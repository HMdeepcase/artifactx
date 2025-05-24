import os
from typing import Optional, List, Dict, Any
from pymilvus import MilvusClient, DataType # DataType might be needed if creating collections, not for search
from pymilvus.exceptions import MilvusException # Import MilvusException for specific error handling
from langchain_core.tools import tool

from config import BaseConfig # To get Milvus URI, DB name, token, and embedding model names
from config import get_global_config
from .embeddings import query2vector # To convert text query to vector

# --- Milvus Client Initialization ---
# Load Milvus configuration
base_cfg = get_global_config()
MILVUS_URI = base_cfg.milvus_uri
MILVUS_DB_NAME = base_cfg.milvus_db_name
MILVUS_TOKEN = getattr(base_cfg, 'milvus_token', None) # Optional token

# Global Milvus client instance
milvus_client_instance: Optional[MilvusClient] = None

def get_milvus_client() -> MilvusClient:
    """Initializes and returns a singleton MilvusClient instance."""
    global milvus_client_instance
    if milvus_client_instance is None:
        print(f"Initializing MilvusClient for URI: {MILVUS_URI}, DB: {MILVUS_DB_NAME}")
        try:
            milvus_client_instance = MilvusClient(
                uri=MILVUS_URI,
                token=MILVUS_TOKEN,
                db_name=MILVUS_DB_NAME
            )
            milvus_client_instance.list_collections() # Test connection
            print("MilvusClient initialized and connection successful.")
        except Exception as e:
            print(f"Error initializing or connecting MilvusClient: {e}")
            milvus_client_instance = None # Ensure it remains None if initialization fails
            # The tool using this will then return an error
    return milvus_client_instance

def get_collection_info(collection_name: str) -> dict:
    """Get detailed information about a collection."""
    try:
        client = get_milvus_client()
        return client.describe_collection(collection_name)
    except Exception as e:
        raise ValueError(f"Failed to get collection info: {str(e)}")

@tool("milvus_list_collections")
def milvus_list_collections() -> str:
    """List all collections in the Milvus database with their schema details."""
    client = get_milvus_client()
    if not client:
        return "Error: Milvus client not available or connection failed."
    try:
        collections = client.list_collections()
        collection_details = ""
        for collection in collections:
            collection_details += f"Collection: {collection}\n"
            try:
                collection_detail = client.describe_collection(collection)
                collection_details += f"{collection_detail}\n"
            except Exception as e:
                collection_details += f"Error retrieving details: {str(e)}\n"
        return f"Collections in database '{MILVUS_DB_NAME}':\n{collection_details}"
    except Exception as e:
        return f"Error listing Milvus collections: {str(e)}"

@tool("milvus_text_image_search")
def milvus_text_image_search(
    query_text: str,
    collection_name: str,
    vector_field: str = "vector",
    limit: int = 5,
    output_fields: Optional[List[str]] = None,
    metric_type: str = "COSINE", 
) -> List[Dict[str, Any]]:
    """
    Searches for images in a Milvus collection using a text query by converting text to a vector.
    Args:
        query_text: The text to search for.
        collection_name: Name of the collection to search.
        vector_field: Field containing vectors to search (default: "vector").
        limit: Maximum number of results to return (default: 5).
        output_fields: Fields to include in results (e.g., ["path", "modality", "metadata"]).
                       Defaults to ["path", "modality", "metadata"] if None.
        metric_type: Distance metric for vector search (default: "COSINE").
    Returns:
        A list of search result dictionaries or an error dictionary.
    """
    if output_fields is None:
        output_fields = ["path", "modality", "metadata"]

    client = get_milvus_client()
    if not client:
        return [{"error": "Milvus client not available or connection failed."}]

    try:
        query_vector_np = query2vector(query_text)
        query_vector_list = query_vector_np.tolist()
    except Exception as e:
        return [{"error": f"Failed to convert query to vector: {str(e)}"}]

    search_params = {
        "metric_type": metric_type,
        "params": {"nprobe": 10} 
    }

    try:
        print(f"Searching collection '{collection_name}' with vector in field '{vector_field}'")
        results = client.search(
            collection_name=collection_name,
            data=[query_vector_list],
            anns_field=vector_field,
            limit=limit,
            search_params=search_params,  # Changed param to search_params
            output_fields=output_fields,
        )
        return results[0] if results else []
    except MilvusException as e:
        # Specific handling for Milvus exceptions (like collection not found)
        return [{"error": f"Milvus vector search failed: {str(e)} (Code: {e.code}, Message: {e.message})"}]
    except Exception as e:
        return [{"error": f"Milvus vector search failed with an unexpected error: {str(e)}"}]

@tool("milvus_text_search")
def milvus_text_search(
    collection_name: str,
    query_text: str,
    text_field_name: str = "content",  # Change this to a field that actually exists in your collection
    limit: int = 5,
    output_fields: Optional[list[str]] = None
) -> str:
    """
    Search for documents using text search in a Milvus collection.
    Uses LIKE operator for basic keyword matching.

    Args:
        collection_name: Name of the collection to search
        query_text: Text to search for
        text_field_name: Field to search within (must be a string field)
        limit: Maximum number of results to return
        output_fields: Fields to include in results
    """
    client = get_milvus_client()
    if not client:
        return "Error: Milvus client not available or connection failed."

    # Create a filter expression using 'LIKE'
    filter_expr = f"{text_field_name} like '%{query_text}%'"

    try:
        results = client.query(  # Note: using query() not search()
            collection_name=collection_name,
            filter=filter_expr,
            limit=limit,
            output_fields=output_fields,
        )
        output = f"Text search results for '{query_text}' in collection '{collection_name}':\n\n"
        for result in results:
            output += f"{result}\n\n"
        return output
    except Exception as e:
        return f"Error: Text search failed: {str(e)}"

milvus_tools = [milvus_list_collections, milvus_text_image_search, milvus_text_search] 