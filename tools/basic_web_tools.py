import requests
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from bs4 import BeautifulSoup
@tool("ip_search")
def ip_search(ip_address: str) -> str:
    """Searches for geographical and network information about a given IP address using the ip-api.com service. The function sends an HTTP GET request to the external API with the specified IP address and returns the API's JSON response. The returned information typically includes the IP's country, region, city, ZIP code, latitude, longitude, timezone, ISP, and organization, among others. If the request fails or an exception occurs, it returns an error object with the failure reason."""
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_address}')
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": True, "message": f"API request failed with status code: {response.status_code}"}
    except Exception as e:
        return {"error": True, "message": str(e)}

@tool("get_website_content")
def get_website_content(url: str, preserve_tags: bool = False) -> str:
    """Get the content of a website by URL. Use if you need to read and verify the contents of a specific website.
    Args:
        url: The URL of the website to get content from
        preserve_tags: If True, returns HTML with tags preserved. If False (default), returns plain text.
    Returns:
        The content as a string.
    """
    headers = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    }
    session = requests.Session()
    session.headers.update(headers)
    response = session.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    if preserve_tags:
        # Return the prettified HTML with tags preserved
        return str(soup.prettify())
    else:
        # Extract text only and remove empty lines
        text = soup.get_text()
        non_empty_lines = [line for line in text.splitlines() if line.strip()]
        return "\n".join(non_empty_lines)[:2500]
    
@tool("web_search")
def web_search(query: str) -> str:
    """Searches the web for the given query using the TavilySearch tool. Returns a list of search results. """
    return TavilySearch(
        max_results=5,
        query=query,
        include_answer=True,
        exclude_domains = ["magnetforensics.com", "stark4n6.com"]
    )

web_tools = [ip_search, web_search, get_website_content]