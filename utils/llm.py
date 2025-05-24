import os
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from config import BaseConfig


def get_llm(cfg: BaseConfig, agent_type="supervisor"):
    """
    Get a language model instance based on configuration.
    
    Args:
        cfg: Configuration object
        agent_type: The type of agent ('supervisor', 'reasoning', 'forensic', 'web')
                    to determine which model config to use
    
    Returns:
        A language model instance (ChatOpenAI or ChatAnthropic)
    """
    # Get model config for the specified agent type
    model_config = cfg.models.get(agent_type, cfg.models.get("forensic"))
    
    # Extract parameters
    model_name = model_config.get("name")
    provider = model_config.get("provider", "").lower()
    temperature = model_config.get("temperature", 0)
    
    # Create and return the appropriate LLM
    if provider == "anthropic":
        return ChatAnthropic(
            model=model_name, 
            temperature=temperature, 
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"), 
            stream_usage=True
        )
    
    # Default to OpenAI
    return ChatOpenAI(
        model=model_name, 
        api_key=os.getenv("OPENAI_API_KEY")
    )