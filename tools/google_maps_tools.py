import os
from langchain_core.tools import tool
import googlemaps
from dotenv import load_dotenv

load_dotenv()
gmaps = googlemaps.Client(key=os.getenv("GOOGLE_API_KEY"))

@tool("google_map_keyword_search")
def google_map_keyword_search(place_str: str) -> str:
    """Searches for the keyword through Google Maps. Returns structured address details including street number, route, locality, administrative regions, country, postal code, and geographic coordinates (latitude/longitude). Also provides a formatted address, place ID, plus code, and location viewport for precise geospatial identification."""
    tmp = gmaps.geocode(place_str, language="en")
    return tmp

@tool("google_map_location_search")
def google_map_location_search(lat: float, lng: float) -> str:
    """Searches using latitude and longitude coordinates through Google Maps and returns detailed geographic information in JSON format, including formatted address, address components (e.g., street number, city, state), place ID, and viewport bounds."""
    location = (lat, lng)
    tmp = gmaps.reverse_geocode(location)
    return tmp

google_maps_tools = [google_map_keyword_search, google_map_location_search]