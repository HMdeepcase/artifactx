import os
import subprocess
try:
    import magic
except ImportError:
    magic = None
from langchain_core.tools import tool
from config import BaseConfig
from config import get_global_config
from setup_logging import get_logger
from pathlib import Path
import json

logger = get_logger(__name__, Path("logs"), level="INFO")

base_cfg = get_global_config()

@tool("read_text_file")
def read_text_file(file_path: str) -> str:
    """Reads the first 5000 characters of a text file in Attachment directory. Use basename for attachments as input. Returns the content as a string."""
    # Normalize path separators to the current OS style
   
    #check if the file is a text file
    if not file_path.endswith(('.txt', '.csv', '.json', '.md', '.log', '.html', '.xml', '.js', '.py', '.cfg', '.conf')):
        return "The file is not a readable text file."
   
    file_path = os.path.normpath(file_path)
    
    # Try file in the attachments directory
    base_dir = base_cfg.get_path("attached_artifact_dir")
    file_path = file_path.replace("\\", "/")
    file_name = file_path.split("/")[-1]
    attachment_path = os.path.join(base_dir, file_name)
    
    if os.path.exists(attachment_path):
        if file_path.endswith('.json'):
            return json.load(open(attachment_path, 'r', encoding='utf-8-sig'))
        else:
            return open(attachment_path, 'r').read()[:5000]
    
    return f"Could not find file: {file_path}. The file may be in the attachments directory {base_dir}."

@tool("search_log_file_with_keywords")
def search_log_file_with_keywords(file_path: str, keywords: str) -> str:
    """
    Searches a log file for specific keywords. Returns the search results as a string. If the file is a .log.gz file, it will be unzipped and searched.
    
    This tool enables keyword search for various log file formats. For regular text log files (such as .log, .evtx, .ps1, .psd1, etc.), the search is performed using the 'grep' command. For compressed log files (such as .log.gz), the tool uses 'zgrep' to search within the compressed file without manual extraction. The appropriate search tool (grep or zgrep) is automatically selected based on the file format, so users can request keyword searches in a unified way regardless of the file type.
    """
    if not file_path.endswith(('.log', '.evtx', 'ps1', 'psd1', '.gz', '.zip', '.7z', '.tar', '.rar')):
        return "The file is not a readable log file."
    import subprocess
    file_path = os.path.normpath(file_path)
    try:
        if file_path.endswith('.log.gz'):
            cmd = ['zgrep', '-H', '-i', '-E', keywords, file_path]
        else:
            cmd = ['grep', '-i', '-E', keywords, file_path]
        completed_process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed_process.returncode == 0 and completed_process.stdout:
            return completed_process.stdout
        else:
            return f"No matches found for '{keywords}' in {file_path}."
    except Exception as e:
        return f"Error searching file: {e}"

@tool("verify_mime_type")
def verify_mime_type(file_path: str) -> str:
    """Verifies if the given file matches the expected MIME type. Can be used to find hidden files. Returns the file type verification result as a string."""
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # Map common extensions to expected MIME types
    extension_to_mime = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.txt': 'text/plain',
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        # Add more mappings as needed
    }
    
    if magic is None:
        logger.warning("python-magic not installed; cannot verify MIME type")
        return "python-magic not installed"

    # Get the actual MIME type using python-magic
    try:
        mime = magic.Magic(mime=True)
        actual_mime = mime.from_file(file_path)
    except Exception as e:
        return f"Error reading file: {e}"
    
    # Get the expected MIME type based on extension
    expected_mime = extension_to_mime.get(file_extension, 'unknown')
    
    # Check if the actual MIME type matches the expected one
    if expected_mime == 'unknown':
        return f"Unsupported file extension: {file_extension}"
    elif actual_mime == expected_mime:
        return f"File type matches: {file_path} is a {actual_mime}"
    else:
        return f"File type mismatch: {file_path} has extension {file_extension} but is actually {actual_mime}"

forensic_tools = [verify_mime_type, read_text_file, search_log_file_with_keywords]
