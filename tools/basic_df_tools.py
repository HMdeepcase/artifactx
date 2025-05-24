import json 
import os
import glob
import re
import pandas as pd
from pathlib import Path
from setup_logging import get_logger
from config import BaseConfig
from config import get_global_config
from langchain.tools import tool
import subprocess

config = get_global_config()

logger = get_logger(__name__, Path("logs"), level="INFO")

@tool()
def get_df_info(df: pd.DataFrame) -> str:
    """Return information about a DataFrame as a string."""
    from io import StringIO
    buffer = StringIO()
    df.info(buf=buffer)
    return buffer.getvalue()

@tool()
def get_df_head(df: pd.DataFrame, n: int = 5) -> str:
    """Return the first ``n`` rows of a DataFrame as CSV."""
    return df.head(n).to_csv(index=False)

@tool("find_csv")
def find_csv() -> str:
    """Searches for CSV files in a specific directory and returns a list of their paths. Useful for retrieving available case-related data files. This tool is useful when you get a all the data files in the directory."""
    # TEST: references nav.html > json
    with open(config.get_path("nav_path"), 'r', encoding='utf-8-sig') as j:
        data = json.load(j)
        return data

# Fix potential path issues
def _resolve_path(p: str) -> str:
    # 1) Absolute path provided and exists
    if os.path.isabs(p) and os.path.exists(p):
        return p

    # 2) Path exists as-is relative to CWD
    if os.path.exists(p):
        return p

    # 3) Fall back to <root_dir>/<p>
    joined = os.path.join(config.get_path("root_dir"), p)
    return joined

def _read_csv(p: str) -> pd.DataFrame:
    file_path = _resolve_path(p)
    if not os.path.exists(file_path):
        return f"Error: File not found at path: {file_path}"
    return pd.read_csv(file_path, low_memory=False)

def _read_json(p: str) -> dict:
    logger.info(f"Reading JSON file from: {p}")
    file_path = _resolve_path(p)
    if not os.path.exists(file_path):
        return f"Error: File not found at path: {file_path}"
    return json.load(open(file_path, 'r', encoding='utf-8-sig'))

# @tool("check_column_names")
# def check_column_names(csv_path: str) -> str:
#     """Reads the specified CSV file and returns a list of all column names.
# This helps users understand the structure of the dataset before making queries.
# It is especially useful before using functions like sort_values or count_values, as it helps you identify the relevant columns to operate on."""
#     df = _read_csv(csv_path)
#     answer = df.columns.tolist()
#     logger.info(f"show_columns: {answer}")
#     # head = df.head(3).to_csv(index=False)
#     # logger.info(f"show_head: {head}")
#     return answer

@tool("sort_values")
def sort_values(csv_path: str, column_name: str, ascending: bool = True) -> str:
    """Sorts the data in the given CSV file by a specified column, in ascending or descending order. Returns the sorted data as a CSV string.
Before using this function, you must call the show_columns function to check the exact column names and ensure that a valid column is provided as the sorting criterion."""
    df = _read_csv(csv_path)
    df[column_name] = df[column_name].fillna('')
    answer = df.sort_values(column_name, ascending=ascending).to_csv(index=False)
    logger.info(f"sort_values: {answer}")
    return answer

# @tool("count_values")
# def count_values(csv_path: str, column_name: str) -> str:
#     """Counts the occurrences of each unique value in a specified column of the CSV file. Returns the counts as a CSV-formatted string.
# Before using this function, you must call the show_columns function to check the exact column names."""
#     df = _read_csv(csv_path)
#     df[column_name] = df[column_name].fillna('')
#     answer = df[column_name].value_counts().to_csv(index=False)
#     logger.info(f"count_values: {answer}")
#     return answer

@tool("find_attachments")
def find_attachments() -> str:
    """Searches for all attachments in the attachments directory and returns a list of their paths."""
    base_dir = config.get_path("attached_artifact_dir")
    all_files = glob.glob(os.path.join(base_dir, "*"))
    # Remove names if they contain "Carved" as we will not get useful information from them
    # also check if the file has a text extension
    all_files = [file for file in all_files if file.endswith(('.txt', '.csv', '.json', '.md', '.log', '.html', '.xml', '.js', '.py', '.cfg', '.conf')) and "Carved" not in file]
    logger.info(f"find_attachments: {all_files}")
    return all_files

@tool("get_relevant_attachments_with_keyword")
def get_relevant_attachments_with_keyword(keyword: str) -> str:
    """Searches for the given keyword in all attachments and returns a list of (attachment filename, count) for files with at least one match."""
    base_dir = config.get_path("attached_artifact_dir")
    # Get all files in the attachments directory
    all_files = glob.glob(os.path.join(base_dir, "*"))
    results = []
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    
    for file_path in all_files:
        if not os.path.isfile(file_path):
            continue
            
        file_name = os.path.basename(file_path)
        count = 0
        # Match in filename
        filename_matches = len(pattern.findall(file_name))
        count += filename_matches
        
        # Try to open and read the file for content matches
        try:
            # First check if it's likely a text file
            # Simple check based on extension - can be improved
            _, ext = os.path.splitext(file_name)
            text_extensions = ['.txt', '.csv', '.json', '.md', '.log', '.html', '.xml', '.js', '.py', '.cfg', '.conf']
            
            # Skip binary files to avoid encoding errors and improve performance
            if ext.lower() in text_extensions:
                # Process the file line by line to handle large files efficiently
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        content_matches = len(pattern.findall(line))
                        count += content_matches
        except Exception as e:
            # Silently skip files that can't be read as text
            pass
        
        if count > 0:
            results.append({"filename": file_name, "count": count})
    
    # Sort results by match count in descending order
    results = sorted(results, key=lambda x: x["count"], reverse=True)
    
    if not results:
        return f"No matches found for keyword '{keyword}' in any attachment files."
    
    # Format the results
    formatted_results = [f"{item['filename']}: {item['count']} matches" for item in results]
    return "\n".join([f"Found {len(results)} files with matches for '{keyword}':", *formatted_results])

@tool("get_relevant_rows_with_keyword")
def get_relevant_rows_with_keyword(csv_path: str, keyword: str) -> str:
    """
    Filters the rows of a CSV file that contain the given keyword in any column.
    Returns matching rows in CSV format.
    """
    df = _read_csv(csv_path)
    df = df.fillna("")
    df = df.astype(str)
    mask = df.apply(
        lambda row: row.str.contains(keyword, case=False, na=False).any(),
        axis=1
    )
    # 5. Filter and serialize to CSV
    filtered = df[mask]

    if filtered.empty:
        return "No rows found with the given keyword."

    if filtered.shape[0] > 50:
        return "There are too many rows to return. Please refine your keyword."

    answer = filtered.to_csv(index=False)

    logger.info(f"get_relevant_rows_with_keyword: {answer}")
    return answer

@tool("keyword_search_in_all_data")
def keyword_search_in_all_data(keyword: str) -> str:
    """Searches for the given keyword in all data files and returns a list of (csv filename, count) for files with at least one match. The search uses the grep command, allowing the use of grep-compatible patterns such as | (alternation) and other regular expressions for advanced keyword matching."""

    # Find all CSV files
    csv_files = glob.glob(os.path.join(config.get_path("root_dir"), '*.csv'))
    # logger.info(f"Found {len(csv_files)} CSV files in {config.get_path("root_dir")}")
    logger.info(f"Looking for keyword: {keyword} in {len(csv_files)} CSV files")
    results = []

    for file_path in csv_files:
        try:
            cmd = ['grep', '-n', '-E', '-i', keyword, file_path]
            completed_process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            lines = completed_process.stdout.strip().split('\n') if completed_process.stdout else []

            for line in lines:
                if not line.strip():
                    continue
                try:
                    parts = line.split(':', 2)
                    if len(parts) == 3:
                        path, lineno, match_text = parts
                        results.append([f"file://{path}", f"L{lineno}", match_text.strip()])
                except Exception as parse_error:
                    logger.warning(f"Failed to parse line: {line} - {parse_error}")

        except Exception as e:
            logger.error(f"Error searching file {file_path}: {str(e)}")

    # Limit to 50
    if len(results) > 50:
        results = results[:50]
        truncated = True
    else:
        truncated = False

    if not results:
        return "No matches found."

    # Manual markdown formatting
    lines = ["| File | Line | Match |", "|------|------|-------|"]
    for row in results:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} |")

    if truncated:
        lines.append("\n⚠️ Output truncated to first 50 matches. Please refine your keyword.")

    return "\n".join(lines)


    # for file_path in csv_files:
    #     try:
    #         # Use grep to count occurrences of the keyword in the file (case-insensitive)
    #         # cmd = ['grep', '-E', '-i', '-o', keyword, file_path]
    #         # cmd = ['grep', '-E', '-i', keyword, file_path]
    #         cmd = ['grep', '-r', '-E', keyword, file_path]
    #         completed_process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    #         logger.info(f"grep result: {completed_process.stdout.strip().split('\n')}")
    #         # Count number of lines matched
    #         count = len(completed_process.stdout.strip().split('\n')) if completed_process.stdout else 0
            
    #         if count > 0:
    #             keyword_set = list(set(completed_process.stdout.strip().split('\n')))
    #             for result_keyword in keyword_set:
    #                 keyword_count = completed_process.stdout.strip().count(result_keyword)
    #                 results.append({"csv_file": os.path.basename(file_path), "count": keyword_count, "keyword": result_keyword})
    #     except Exception as e:
    #         logger.error(f"Error searching file {file_path}: {str(e)}")
    
    # results.sort(key=lambda x: x["count"], reverse=True)
    # logger.info(f"keyword_search_in_all_data results: {results}")
    # return results

    #     try:
    #         # Open file and search line by line without loading entire file
    #         with open(file, 'r', encoding='utf-8', errors='ignore') as f:
    #             for line in f:
    #                 # Count occurrences in this line
    #                 matches = len(re.findall(keyword, line, re.IGNORECASE))
    #                 count += matches
    #         if count >= 1:
    #             results.append({"csv_file": os.path.basename(file), "count": count})
    #     except Exception as e:
    #         logger.error(f"Error searching file {file}: {str(e)}")
    
    # # Sort results by match count in descending order
    # results = sorted(results, key=lambda x: x["count"], reverse=True)

    # logger.info(f"keyword_search_in_all_data results: {results}")
    # return results

@tool("filter_by_date_or_time")
def filter_by_date_or_time(csv_path: str, column_name: str, start_date: str, end_date: str) -> str:
    """Filters rows in the CSV file where the specified date column matches either the given start date or end date. Returns matching entries as a CSV string. Write the start and end date in the same format with the csv file."""
    df = _read_csv(csv_path)
    df[column_name] = df[column_name].fillna('')
    
    # 날짜 범위 내의 데이터 필터링
    filtered_df = df[
        (df[column_name] >= start_date) & 
        (df[column_name] < end_date)
    ]
    
    answer = filtered_df.to_csv(index=False)
    # Limit to 1000
    if len(answer) > 1000:
        answer = answer[:1000]
        truncated = True
    else:
        truncated = False
    
    if truncated:
        answer += "\n⚠️ Output truncated to first 1000 rows. Please refine your date range."
        
    logger.info(f"filter_by_date_or_time: {answer}")
    return answer

@tool("find_reference_index")
def find_reference_index() -> list[str]:
    """Returns a list of available artifact keywords from the knowledge data JSON file.
This helps the agent recommend relevant keywords when the user is unsure which CSV file to query.
After retrieving the keyword list, you can use the find_reference_data tool to look up corresponding reference data.
Note: the keyword must be written exactly as listed to retrieve the correct data.
    """
    data = _read_json(config.knowledge_data_path)
    index_lst = [key for key in data.keys()]
    logger.info("find_reference_index: %s", index_lst)
    return index_lst

@tool("find_reference_data")
def find_reference_data(keyword: str) -> str:
    """Retrieves reference data from the knowledge data JSON file based on a specified keyword.
Before using this function, you must first call find_reference_index to check the list of available keywords.
This function requires an exact match with one of those keywords.
Returns the corresponding reference data as a string."""
    data = _read_json(config.knowledge_data_path)
    target_data = [val for key, val in data.items() if key == keyword]
    return target_data

df_tools = [find_csv, find_attachments, sort_values, get_relevant_attachments_with_keyword, get_relevant_rows_with_keyword, filter_by_date_or_time, find_reference_index, find_reference_data, keyword_search_in_all_data]
