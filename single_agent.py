import os, asyncio, uuid, json, argparse, sys
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, List, Any, TypedDict, Optional

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from setup_logging import get_logger
from config import BaseConfig, MCPConfig
from config import set_global_config
from tools import basic_tools
from utils.llm import get_llm
from utils.evaluator import ForensicEvaluator
from utils.message_parser import extract_artifacts_from_message, extract_reasoning_from_message, validate_artifacts_exist

load_dotenv()

class AgentState(TypedDict):
    messages: List[Dict[str, Any]]
    artifacts: List[str]  # Store artifacts found by the agent
    reasoning: str  # Store reasoning process


def with_forensic_prompt(state):
    system_msg = (
        "You are a digital forensics expert. Your job is to analyze digital evidence "
        "using the available tools to find artifacts, extract data, and provide comprehensive analysis. "
        "You will directly execute searches, examine files, and gather evidence to answer the user's questions. "
        "Be thorough in your investigation and provide detailed explanations of your findings."
        "\n\nCRITICAL REQUIREMENT - ARTIFACTS SECTION: When providing your final answer, you MUST include the EXACT filenames with extensions "
        "of any data files, artifact files, or evidence sources you selected and analyzed to answer the question. "
        "DO NOT simplify, abbreviate, or change filenames in any way - use them EXACTLY as found "
        "(e.g., 'Edge Chromium Web History.csv' not just 'Browser History.csv'). "
        "Under no circumstances should you add filenames that you did not use or are not in the system."
        "\n\nThe ARTIFACTS section MUST contain the specific CSV, JSON, LOG, or other data files you actually opened and analyzed. "
        "For example, if you analyzed browser history, list 'Chrome Web History.csv' and 'Edge Chromium Web History.csv', "
        "not just 'browser history'. If you found nothing relevant in a file, do NOT list it."
        "\n\nAfter completing your investigation, provide your answer in this EXACT format:\n"
        "===ANSWER===\n[Your detailed analysis and findings here]\n\n"
        "===ARTIFACTS===\n[List each data file you actually used with exact filenames including extensions]"
    )
    return [{"role": "system", "content": system_msg}] + state["messages"]


async def process_single_query(agent, query, cfg, local_logger=None):
    """Process a single query and return the result."""
    # Use the provided logger or fall back to the module-level logger
    log = local_logger or logger
    
    if not log:
        # If no logger is available, create a simple console logger
        import logging
        logging.basicConfig(level=logging.INFO)
        log = logging.getLogger("process_single_query")
    
    log.info("Starting new query processing...")
    
    # Initialize agent state to track artifacts and reasoning
    agent_state = {"artifacts": [], "reasoning": ""}
    
    try:
        log.info("Using invoke to process query")
        
        # Execute the agent
        result = agent.invoke(
            {"messages": [HumanMessage(content=query)]}, 
            cfg
        )
        
        # Check if we got a result with messages
        if isinstance(result, dict) and "messages" in result:
            answer = result["messages"][-1].content if result["messages"] else "No response generated"
            
            # Extract artifacts only from the final answer
            artifacts = extract_artifacts_from_message(answer)
            if artifacts:
                log.info(f"Raw artifacts mentioned in final answer: {artifacts}")
                # Validate that artifacts actually exist in the system
                validated_artifacts = validate_artifacts_exist(artifacts, base_cfg)
                agent_state["artifacts"] = validated_artifacts
                
                if len(validated_artifacts) != len(artifacts):
                    missing_artifacts = set(artifacts) - set(validated_artifacts)
                    log.warning(f"Some artifacts were not found in system: {missing_artifacts}")
                    log.info(f"Validated artifacts: {validated_artifacts}")
                else:
                    log.info(f"All artifacts validated: {validated_artifacts}")
            else:
                log.info("No artifacts found in final answer")
            
            # Extract reasoning from all messages (we want the full reasoning process)
            for message in result.get("messages", []):
                if hasattr(message, "content") and message.content:
                    # First try to extract formal REASONING sections
                    reasoning = extract_reasoning_from_message(message.content)

                    if not reasoning and message != result["messages"][-1]:
                        # Skip system messages and just get the substantive content
                        content = message.content.strip()
                        if content and not content.startswith("I need to") and len(content) > 20:
                            reasoning = content
                    
                    # Add any reasoning found to our accumulated reasoning
                    if reasoning:
                        if agent_state["reasoning"]:
                            agent_state["reasoning"] += "\n\n" + reasoning
                        else:
                            agent_state["reasoning"] = reasoning
            
            # Create metadata for evaluator
            metadata = {
                "artifacts": agent_state["artifacts"],
                "reasoning": agent_state["reasoning"]
            }
            
            log.info(f"Final artifacts found: {agent_state['artifacts']}")
            if agent_state["reasoning"]:
                log.info(f"Reasoning length: {len(agent_state['reasoning'])}")
            
            return answer, metadata
            
    except Exception as e:
        log.error(f"Error during processing: {str(e)}")
    
    # Fallback
    log.error("Failed to process query")
    return "Failed to generate a response", {"artifacts": [], "reasoning": ""}


async def run_single_agent(evaluate=False, interactive=True, output_file=None, enable_mcp=False):
    thread_id = uuid.uuid4().hex
    
    # Setup model for the agent
    llm_forensic = get_llm(base_cfg, "forensic")

    # Load MCP configuration only if requested
    mcp_cfg = None
    if enable_mcp:
        try:
            mcp_cfg = MCPConfig()
            logger.info(f"Loaded MCP configuration: {list(mcp_cfg.data.keys())}")
        except Exception as e:
            logger.warning(f"Could not load MCP configuration: {e}")
            logger.info("Continuing with basic tools only")
    else:
        logger.info("MCP disabled - using basic tools only")

    # Combine all tools for the single agent
    all_tools = []
    
    # Add basic tools first
    if isinstance(basic_tools, dict):
        for tool_group in basic_tools.values():
            if isinstance(tool_group, list):
                all_tools.extend(tool_group)
            else:
                all_tools.append(tool_group)
    elif isinstance(basic_tools, list):
        all_tools = basic_tools
    else:
        all_tools = [basic_tools]

    # Add MCP tools if configuration is available
    if mcp_cfg is not None:
        try:
            async with MultiServerMCPClient(mcp_cfg.data) as mcp_client:
                # Get tools from the MCP server
                mcp_tools = mcp_client.get_tools()
                all_tools.extend(mcp_tools)
                logger.info(f"Added {len(mcp_tools)} MCP tools")
                
                # Create the single forensic agent with all tools (basic + MCP)
                forensic_agent = create_react_agent(
                    llm_forensic,
                    all_tools,
                    checkpointer=MemorySaver(),
                    prompt=with_forensic_prompt,
                    name="forensic_agent",
                )

                cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": base_cfg.recursion_limit}
                logger.info(f"Using thread_id {thread_id} for this session")
                
                # Run the main logic within the MCP context
                return await _run_agent_logic(forensic_agent, cfg, evaluate, interactive, output_file)
                
        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}")
            logger.info("Falling back to basic tools only")
    
    # Fallback: Create agent with basic tools only
    forensic_agent = create_react_agent(
        llm_forensic,
        all_tools,
        checkpointer=MemorySaver(),
        prompt=with_forensic_prompt,
        name="forensic_agent",
    )

    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": base_cfg.recursion_limit}
    logger.info(f"Using thread_id {thread_id} for this session (basic tools only)")
    
    return await _run_agent_logic(forensic_agent, cfg, evaluate, interactive, output_file)


async def _run_agent_logic(forensic_agent, cfg, evaluate=False, interactive=True, output_file=None):
    """Extracted agent logic that can be run with or without MCP tools."""
    # Evaluation mode
    if evaluate:
        # Create evaluator from config and pass our logger to it
        evaluator = ForensicEvaluator(base_cfg, logger=logger)
        
        # Create a function to process queries
        async def process_question(question):
            logger.info(f"Processing question: {question[:50]}...")
            answer, metadata = await process_single_query(forensic_agent, question, cfg, local_logger=logger)
            logger.info(f"AGENT ANSWER: {answer}")
            return answer, metadata
        
        # Run the evaluation by processing each question individually
        results = None
        output_path = None
        
        try:
            # Process all questions in the evaluator
            for i, question in enumerate(evaluator.questions):
              
                answer, metadata = await process_question(question)
                evaluation = evaluator.evaluate_answer(question, answer, metadata)
                evaluator.log_evaluation_details(evaluation)
            
            # Save the results
            results = evaluator.get_results_summary()
            output_path = evaluator.save_results(f"{base_cfg.get_path('output_dir')}/{output_file}")
            
            logger.info("Evaluation complete!")
            logger.info(f"Results saved to {output_path}")
            logger.info(f"Retrieval accuracy: {results['retrieval_accuracy']:.2f}%")
            logger.info(f"Answer accuracy: {results['answer_accuracy']:.2f}%")
            
        except Exception as e:
            logger.error(f"Error during evaluation: {e}")
            raise
        
        return results, output_path
    
    # Interactive mode
    if interactive:
        while True:
            user_input = input("Enter your query (or type 'exit' to quit): ").strip()
            if user_input.lower() in {"exit", "quit", "q"}:
                logger.info("Exiting...")
                break

            try:
                # Process the query and get the final answer
                answer, metadata = await process_single_query(forensic_agent, user_input, cfg, local_logger=logger)
                
                # Print the final answer
                logger.info("\n=== FINAL ANSWER ===")
                logger.info(answer)

                if metadata["artifacts"]:
                    logger.info("\n=== ARTIFACTS USED ===")
                    for artifact in metadata["artifacts"]:
                        logger.info(f"- {artifact}")
                
                # Optionally print reasoning if requested
                logger.info("\nType 'reasoning' to see the agent reasoning or press enter to continue.")
                show_reasoning = input("> ").strip().lower()
                if show_reasoning == "reasoning" and metadata["reasoning"]:
                    logger.info("\n=== REASONING ===")
                    logger.info(metadata["reasoning"])
                
            except Exception as e:
                logger.error(f"Error processing query: {e}")
                logger.info(f"An error occurred: {e}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Digital Forensics Single Agent")
    parser.add_argument("--evaluate", action="store_true", help="Run in evaluation mode")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--log-level", type=str, default="INFO", 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                        help="Set the logging level")
    parser.add_argument("--config", type=str, default="config.json", help="Path to the config file")
    parser.add_argument("--enable-mcp", action="store_true", help="Enable MCP tools (requires MCP server to be running)")
    parser.add_argument("--list-mcp-tools", action="store_true", help="List available MCP tools and exit")
    
    args = parser.parse_args()
    
    # Default to interactive if neither mode is specified
    if not args.evaluate and not args.interactive:
        args.interactive = True
    
    base_cfg = BaseConfig(args.config)
    set_global_config(base_cfg)
    logger = None

    # Ensure required directories exist
    log_dir = Path(base_cfg.get_path("log_dir"))
    output_dir = Path(base_cfg.get_path("output_dir"))
    
    # Create directories if they don't exist
    log_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging
    session_id = uuid.uuid4().hex
    logger = get_logger(__name__, log_dir, level=args.log_level, session_id=session_id, case_name=base_cfg.case_name)
    logger.info("ArtifactX is starting...")
    
    # Handle MCP tools listing if requested
    if args.list_mcp_tools:
        try:
            mcp_cfg = MCPConfig()
            logger.info(f"MCP Configuration loaded from: config/mcp_servers.json")
            logger.info(f"Available MCP servers: {list(mcp_cfg.data.keys())}")
            
            async def list_mcp_tools():
                try:
                    async with MultiServerMCPClient(mcp_cfg.data) as mcp_client:
                        mcp_tools = mcp_client.get_tools()
                        logger.info(f"\nFound {len(mcp_tools)} MCP tools:")
                        for i, tool in enumerate(mcp_tools, 1):
                            logger.info(f"  {i}. {tool.name}: {tool.description}")
                        return True
                except Exception as e:
                    logger.info(f"Error connecting to MCP servers: {e}")
                    return False
            
            success = asyncio.run(list_mcp_tools())
            sys.exit(0 if success else 1)
        except Exception as e:
            print(f"Error loading MCP configuration: {e}")
            sys.exit(1)
    
    try:
        result = asyncio.run(run_single_agent(
            evaluate=args.evaluate, 
            interactive=args.interactive,
            output_file=f"evaluation_results_{base_cfg.case_name}_{session_id}.json",
            enable_mcp=args.enable_mcp
        ))
        
        # Print the output file path if in evaluation mode
        if args.evaluate and isinstance(result, tuple) and len(result) > 1:
            _, output_path = result
            print(f"\nEvaluation results saved to: {output_path}")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
