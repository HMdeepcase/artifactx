"""
Message parsing utilities for extracting artifacts and reasoning from agent messages.
"""

import re
import os
from typing import List
from pathlib import Path


def validate_artifacts_exist(artifacts: List[str], config) -> List[str]:
    """
    Validate that the reported artifacts actually exist in the system.
    
    Args:
        artifacts: List of artifact filenames to validate
        config: Configuration object to get file paths
        
    Returns:
        List of artifacts that actually exist in the system
    """
    if not artifacts:
        return []
    
    validated_artifacts = []
    
    # Get the case directory paths
    try:
        root_dir = config.get_path("root_dir")  # e.g., test/backup/case_2022_windows/Export
        base_paths = [
            Path(root_dir),
            Path(root_dir) / "Attachments",
            Path(root_dir).parent,  # case directory
        ]
        
        # Also check common subdirectories
        for base_path in list(base_paths):
            if base_path.exists():
                for subdir in base_path.iterdir():
                    if subdir.is_dir():
                        base_paths.append(subdir)
        
    except Exception:
        # Fallback to common paths if config fails
        base_paths = [
            Path("test/backup"),
            Path("test/Export"), 
            Path("Export"),
            Path("."),
        ]
    
    for artifact in artifacts:
        found = False
        
        # Check in all possible base paths
        for base_path in base_paths:
            if not base_path.exists():
                continue
                
            # Try exact match first
            artifact_path = base_path / artifact
            if artifact_path.exists():
                validated_artifacts.append(artifact)
                found = True
                break
            
            # Try recursive search for the filename
            try:
                for file_path in base_path.rglob(artifact):
                    if file_path.is_file():
                        validated_artifacts.append(artifact)
                        found = True
                        break
                if found:
                    break
            except (PermissionError, OSError):
                # Skip directories we can't access
                continue
        
        if not found:
            # Log missing artifact but don't include it
            print(f"Warning: Artifact '{artifact}' not found in file system")
    
    return validated_artifacts


def extract_artifacts_from_message(message_content: str) -> List[str]:
    """
    Extract artifact filenames from a message content.
    
    Args:
        message_content: The content of the message to parse
        
    Returns:
        List of unique artifact filenames found in the message
    """
    artifacts = []
    
    # Look for filenames in the "ARTIFACTS:" section if present
    artifacts_section = re.search(r"ARTIFACTS:(.*?)(?:REASONING:|$)", message_content, re.DOTALL | re.IGNORECASE)
    if artifacts_section:
        section_text = artifacts_section.group(1).strip()
        # Extract filenames that match patterns like *.csv, *.txt, etc.
        filename_matches = re.findall(r"[\w\s\-]+\.(csv|txt|log|json|xml|html|db|sqlite)", section_text, re.IGNORECASE)
        artifacts.extend([match.strip() for match in filename_matches if match.strip()])
    
    # Also look for explicit filenames in the general text
    general_filenames = re.findall(r"['\"]?([\w\s\-]+\.(csv|txt|log|json|xml|html|db|sqlite))['\"]?", 
                                  message_content, re.IGNORECASE)
    if general_filenames:
        artifacts.extend([match[0].strip() for match in general_filenames if match[0].strip()])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_artifacts = []
    for item in artifacts:
        if item not in seen:
            seen.add(item)
            unique_artifacts.append(item)
    
    return unique_artifacts


def extract_reasoning_from_message(message_content: str) -> str:
    """
    Extract reasoning section from a message.
    
    Args:
        message_content: The content of the message to parse
        
    Returns:
        The reasoning text if found, empty string otherwise
    """
    reasoning = ""
    
    # Look for the reasoning section
    reasoning_match = re.search(r"REASONING:(.*?)(?:ARTIFACTS:|$)", message_content, re.DOTALL | re.IGNORECASE)
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()
    
    return reasoning


def process_agent_message(message, agent_state: dict) -> dict:
    """
    Process an agent's message to extract artifacts and reasoning.
    
    Args:
        message: The message object with content attribute
        agent_state: Dictionary containing artifacts and reasoning lists
        
    Returns:
        Updated agent_state dictionary
    """
    if hasattr(message, "content") and message.content:
        # Extract artifacts
        artifacts = extract_artifacts_from_message(message.content)
        if artifacts:
            agent_state["artifacts"].extend(artifacts)
            # Remove duplicates while preserving order
            seen = set()
            agent_state["artifacts"] = [x for x in agent_state["artifacts"] if x not in seen and not seen.add(x)]
        
        # Extract reasoning
        reasoning = extract_reasoning_from_message(message.content)
        if reasoning:
            if agent_state["reasoning"]:
                agent_state["reasoning"] += "\n\n" + reasoning
            else:
                agent_state["reasoning"] = reasoning
    
    return agent_state 