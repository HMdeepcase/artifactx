import json
import os
import uuid
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from langchain_openai import ChatOpenAI

class ForensicEvaluator:
    """
    Evaluator for digital forensic question answering.
    Compares agent answers with ground truth and calculates accuracy metrics.
    """
    
    def __init__(self, config, case_name=None, logger=None):
        """
        Initialize the evaluator.
        
        Args:
            config: Configuration object with model settings
            case_name: Optional case name to override config
            logger: Required logger instance to use
        """
        self.config = config
        self.case_name = case_name or config.case_name
        
        # Use the provided logger
        self.logger = logger
        if not self.logger:
            raise ValueError("Logger must be provided to ForensicEvaluator")
        
        # Get ground truth path using config helper
        ground_truth_path = config.get_path("ground_truth_path")
        self.ground_truth_path = Path(ground_truth_path)
        
        # Initialize evaluator model
        model_config = config.models.get("evaluator", config.models.get("supervisor"))
        model_name = model_config.get("name")
        temperature = model_config.get("temperature", 0)
        self.evaluator_model = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Load ground truth (which contains the questions)
        self.ground_truth = self._load_ground_truth()
        
        # Extract questions from ground truth
        self.questions = [item["question"] for item in self.ground_truth]
        
        # Create a lookup dictionary for ground truth by question text
        self.ground_truth_by_question = {item["question"]: item for item in self.ground_truth}
        
        # Results storage
        self.results = {
            "total_questions": len(self.questions),
            "correct_retrievals": 0,
            "correct_answers": 0,
            "evaluations": []
        }
    
    def _load_ground_truth(self) -> List[Dict[str, Any]]:
        """Load ground truth answers from JSON file."""
        if not self.ground_truth_path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {self.ground_truth_path}")
        
        with open(self.ground_truth_path, 'r') as f:
            return json.load(f)
    
    def evaluate_answer(self, question: str, agent_answer: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate an agent's answer against ground truth.
        
        Args:
            question: The question asked
            agent_answer: The agent's answer
            metadata: Optional metadata containing artifacts and reasoning
            
        Returns:
            Evaluation result dictionary
        """
        if not self.ground_truth or question not in self.ground_truth_by_question:
            # No ground truth for comparison
            return {
                "question": question,
                "agent_answer": agent_answer,
                "evaluation": "No ground truth available for comparison"
            }
        
        truth = self.ground_truth_by_question[question]
        question_id = truth.get("no", 0)
        expected_artifacts = truth.get("related_artifacts", [])
        expected_answer = truth.get("answer", "")
        
        # Check for artifact retrieval - success if ANY of the expected artifacts are mentioned
        artifacts_correct = False
        found_artifacts = []
        
        # Check if we have retrieved artifacts from agents
        retrieved_artifacts = []
        agent_reasoning = ""
        if metadata and isinstance(metadata, dict):
            retrieved_artifacts = metadata.get("artifacts", [])
            agent_reasoning = metadata.get("reasoning", "")
            
            # Log the artifacts we found from agents
            if retrieved_artifacts:
                self.logger.info(f"Found {len(retrieved_artifacts)} retrieved artifacts: {retrieved_artifacts}")
        
        # Combined search scope - check both the answer text and the retrieved artifacts
        if not expected_artifacts:
            # If no artifacts are expected, consider it correct
            artifacts_correct = True
        else:
            # Check retrieved artifacts first (more reliable)
            for expected in expected_artifacts:
                for found in retrieved_artifacts:
                    # Exact match
                    if expected == found:
                        artifacts_correct = True
                        found_artifacts.append(found)
                        break
                        
                    # Check for base name match (without extension)
                    expected_base = os.path.splitext(expected)[0]
                    found_base = os.path.splitext(found)[0]
                    if expected_base and found_base and expected_base == found_base:
                        artifacts_correct = True
                        found_artifacts.append(f"{found} (matched with {expected})")
                        break
                        
                    # Flexible matching with regex
                    import re
                    pattern = re.escape(expected).replace("\\ ", "\\s+")
                    if re.search(pattern, found, re.IGNORECASE):
                        artifacts_correct = True
                        found_artifacts.append(f"{found} (regex match with {expected})")
                        break
            
            # If not found in retrieved artifacts, also check the answer text
            if not artifacts_correct:
                for artifact in expected_artifacts:
                    # Check for exact matches
                    if artifact in agent_answer:
                        artifacts_correct = True  # Success with just one match
                        found_artifacts.append(artifact)
                        continue
                    
                    # Check for common variations
                    # 1. Without file extension
                    base_name = os.path.splitext(artifact)[0]
                    if base_name and base_name in agent_answer:
                        artifacts_correct = True  # Success with just one match
                        found_artifacts.append(f"{base_name} (from {artifact})")
                        continue
                        
                    # 2. With different spacing/capitalization
                    import re
                    # Replace spaces with flexible whitespace in regex
                    pattern = re.escape(artifact).replace("\\ ", "\\s+")
                    # Make it case insensitive
                    if re.search(pattern, agent_answer, re.IGNORECASE):
                        artifacts_correct = True  # Success with just one match
                        found_artifacts.append(f"{artifact} (regex match)")
                        continue
        
        # Use evaluator model to check answer
        prompt = f"""
        Question: {question}
        
        Ground Truth Answer: {expected_answer}
        
        Agent's Answer: {agent_answer}
        """
        
        # Include full reasoning in prompt if available
        if agent_reasoning:
            prompt += f"\n\nAgent's Investigation Process and Reasoning:\n{agent_reasoning}"
            
        prompt += f"""
        
        Task: Evaluate the agent's forensic investigation and answer quality.
        
        Instructions:
        1. Compare the agent's final answer to the ground truth answer for factual correctness
        2. Assess the investigation methodology and reasoning process:
           - Did the agent search appropriate data sources?
           - Was the reasoning logical and systematic?
           - Did the agent properly analyze the evidence?
           - Were any critical steps missed in the investigation?
        3. Consider if the wrong answer resulted from poor reasoning vs. missing/inaccessible data
        
        Expected Data Sources: {', '.join(expected_artifacts) if expected_artifacts else 'Any relevant sources'}
        Agent Used: {', '.join(retrieved_artifacts) if retrieved_artifacts else 'No specific sources listed'}
        
        Return a JSON with these fields:
        1. found_answer (string): The answer found by the agent
        2. answer_correct (boolean): Whether the answer matches the ground truth
        3. evaluation (string): Detailed evaluation covering both factual accuracy and investigation quality, including assessment of the reasoning process and methodology used
        """
        
        evaluation_response = self.evaluator_model.invoke(prompt)
        evaluation_text = evaluation_response.content
        
        # Extract JSON from response (handling potential formatting issues)
        try:
            import re
            json_match = re.search(r'({.*})', evaluation_text.replace('\n', ' '), re.DOTALL)
            if json_match:
                evaluation = json.loads(json_match.group(1))
            else:
                evaluation = {
                    "found_answer": "",
                    "answer_correct": False,
                    "evaluation": "Could not parse evaluation response"
                }
        except Exception as e:
            evaluation = {
                "found_answer": "",
                "answer_correct": False,
                "evaluation": f"Error parsing evaluation: {str(e)}"
            }
        
        # Update metrics
        if artifacts_correct:
            self.results["correct_retrievals"] += 1

        if evaluation.get("answer_correct", False):
            self.results["correct_answers"] += 1

        # If no artifacts were matched but we have retrieved artifacts, use them as found_artifacts
        if not found_artifacts and retrieved_artifacts:
            found_artifacts = retrieved_artifacts.copy()
            self.logger.info(f"No matching artifacts found, but agent retrieved: {retrieved_artifacts}")

        result = {
            "id": question_id,
            "question": question,
            "agent_answer": agent_answer,
            "expected_artifacts": expected_artifacts,
            "found_artifacts": found_artifacts,
            "expected_answer": expected_answer,
            "found_answer": evaluation.get("found_answer", ""),
            "artifact_retrieval_correct": artifacts_correct,
            "answer_correct": evaluation.get("answer_correct", False),
            "evaluation": evaluation.get("evaluation", "")
        }
        
        self.results["evaluations"].append(result)
        return result
    
    def log_evaluation_details(self, evaluation: Dict[str, Any]) -> None:
        """
        Log detailed information about an evaluation result.
        
        Args:
            evaluation: Evaluation result dictionary from evaluate_answer
        """
        question_id = evaluation.get('id', 'N/A')
        expected_artifacts = evaluation.get("expected_artifacts", [])
        found_artifacts = evaluation.get("found_artifacts", [])
        answer = evaluation.get("agent_answer", "")
        
        artifact_status = "✅" if evaluation.get("artifact_retrieval_correct", False) else "❌"
        answer_status = "✅" if evaluation.get("answer_correct", False) else "❌"
        
        self.logger.info(f"Question {question_id} evaluation:")
        self.logger.info(f"  Artifact Retrieval: {artifact_status} (at least one artifact needed)")
        self.logger.info(f"  Answer: {answer_status}")
        
        if expected_artifacts:
            self.logger.info(f"  - Expected artifacts (any of): {', '.join(expected_artifacts)}")
            
            # Log retrieved artifacts if present
            retrieved_artifacts = evaluation.get("artifacts", [])
            if retrieved_artifacts:
                self.logger.info(f"  - Retrieved artifacts: {', '.join(retrieved_artifacts)}")
                self.logger.info("  - Retrieved artifact matches:")
                for expected in expected_artifacts:
                    if expected in retrieved_artifacts:
                        self.logger.info(f"    ✅ Found exact match '{expected}' in retrieved artifacts")
                    else:
                        # Check for base name matches
                        expected_base = os.path.splitext(expected)[0]
                        for artifact in retrieved_artifacts:
                            found_base = os.path.splitext(artifact)[0]
                            if expected_base and found_base and expected_base == found_base:
                                self.logger.info(f"    ✅ Found base name match '{artifact}' for '{expected}'")
                                break
                        else:
                            self.logger.info(f"    ❌ Did NOT find '{expected}' in retrieved artifacts")
            
            # Debug: Search for artifacts in the answer
            self.logger.info("  - Text search details:")
            for artifact in expected_artifacts:
                if artifact in answer:
                    self.logger.info(f"    ✅ Found '{artifact}' in the answer text")
                else:
                    self.logger.info(f"    ❌ Did NOT find '{artifact}' in the answer text")
                    # Show nearby context to help debug
                    artifact_parts = artifact.split('.')
                    if len(artifact_parts) > 1:
                        base_name = artifact_parts[0]
                        if base_name in answer:
                            self.logger.info(f"      (But found partial match '{base_name}' in the answer)")
            
            if found_artifacts:
                self.logger.info(f"  - Found artifacts: {', '.join(found_artifacts)}")
            else:
                self.logger.info(f"  - No matching artifacts found")
        
        self.logger.info(f"  Evaluation: {evaluation.get('evaluation', 'No evaluation provided')}")
    
    def run_evaluation(self, query_processor, config):
        """
        Run a complete evaluation against all questions in the ground truth.
        
        Args:
            query_processor: Async function that processes a query and returns an answer
            config: Configuration to pass to the query processor
            
        Returns:
            Tuple of (results summary, output file path)
        """
        self.logger.info("Starting evaluation...")
        self.logger.info(f"Using ground truth file: {self.ground_truth_path}")
        
        total_questions = len(self.questions)
        self.logger.info(f"Found {total_questions} questions to evaluate")
        
        for i, question in enumerate(self.questions):
            self.logger.info(f"Processing question {i+1}/{total_questions} (ID: {self.ground_truth_by_question.get(question, {}).get('id', 'N/A')}): {question[:50]}...")
            
            # Process the question
            result = yield query_processor(question, config)
            
            # Handle different return types (simple string or tuple with metadata)
            if isinstance(result, tuple) and len(result) >= 2:
                answer, metadata = result
            else:
                answer = result
                metadata = None
            
            # Log the complete answer for debugging
            self.logger.info(f"AGENT ANSWER: {answer}")
            
            # Evaluate the answer with metadata if available
            evaluation = self.evaluate_answer(question, answer, metadata)
            
            # Log detailed evaluation information
            self.log_evaluation_details(evaluation)
        
        # Get and return results summary
        results = self.get_results_summary()
        self.logger.info("Evaluation complete!")
        self.logger.info(f"Retrieval accuracy: {results['retrieval_accuracy']:.2f}%")
        self.logger.info(f"Answer accuracy: {results['answer_accuracy']:.2f}%")
        
        return results
    
    def get_results_summary(self) -> Dict[str, Any]:
        """Get a summary of evaluation results."""
        total = max(1, self.results["total_questions"])  # Avoid division by zero
        
        return {
            "total_questions": total,
            "correct_retrievals": self.results["correct_retrievals"],
            "retrieval_accuracy": (self.results["correct_retrievals"] / total) * 100,
            "correct_answers": self.results["correct_answers"],
            "answer_accuracy": (self.results["correct_answers"] / total) * 100,
            "evaluations": self.results["evaluations"]
        }
    
    def save_results(self, output_path: Optional[str] = None) -> str:
        """
        Save evaluation results to a JSON file.
        
        Args:
            output_path: Optional custom path for evaluation results
            
        Returns:
            The path where the results were saved
        """
        if output_path is None:
            # Generate a default path in the logs directory
            log_dir = self.config.get_path("log_dir")
            timestamp = uuid.uuid4().hex[:8]
            output_path = f"{log_dir}/evaluation_{self.case_name}_{timestamp}.json"
        
        # Handle both relative and absolute paths
        if not os.path.isabs(output_path):
            # If it's a relative path, make it relative to the current directory
            output_path = os.path.join(os.getcwd(), output_path)
        
        # Make sure the directory exists
        directory = os.path.dirname(output_path)
        if directory:  # Only create directory if there is one specified
            os.makedirs(directory, exist_ok=True)
        
        # Save results
        with open(output_path, 'w') as f:
            json.dump(self.get_results_summary(), f, indent=2)
            
        return output_path 