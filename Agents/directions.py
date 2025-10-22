import os
import openrouteservice
from openrouteservice import exceptions
from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import tool
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
load_dotenv()
# --- OpenRouteService Client Initialization ---
ORS_API_KEY = os.getenv("ORS_API_KEY")

try:
    if not ORS_API_KEY:
        print("⚠️ WARNING: OpenRouteService API key not found in environment variables (ORS_API_KEY)")
        ors_client = None
    else:
        ors_client = openrouteservice.Client(key=ORS_API_KEY)
        print("✅ OpenRouteService client initialized successfully")
except Exception as e:
    print(f"❌ OpenRouteService Client Initialization failed: {e}")
    ors_client = None

# --- Define Pydantic Schema ---
# We need coordinates (longitude, latitude) for OpenRouteService
# The LLM might provide place names, so we'll add a geocoding step if needed.

class Coordinates(BaseModel):
    longitude: float
    latitude: float

class DirectionsSchema(BaseModel):
    """Input parameters for getting directions using OpenRouteService."""
    start_location_name: Optional[str] = Field(None, description="Name of the starting location (e.g., 'Hotel Le Djoloff, Dakar'). Provide this OR start_coords.")
    end_location_name: Optional[str] = Field(None, description="Name of the ending location (e.g., 'IFAN Museum of African Arts, Dakar'). Provide this OR end_coords.")
    start_coords: Optional[Coordinates] = Field(None, description="Coordinates of the starting location (longitude, latitude). Provide this OR start_location_name.")
    end_coords: Optional[Coordinates] = Field(None, description="Coordinates of the ending location (longitude, latitude). Provide this OR end_location_name.")
    profile: str = Field("driving-car", description="Mode of transport. Options: 'driving-car', 'driving-hgv', 'foot-walking', 'foot-hiking', 'cycling-regular', 'cycling-road', 'cycling-mountain', 'cycling-electric'.")

    @field_validator('*', mode='before')
    def check_location_provided(cls, values):
        start_name, start_coords = values.get('start_location_name'), values.get('start_coords')
        end_name, end_coords = values.get('end_location_name'), values.get('end_coords')
        if not start_name and not start_coords:
            raise ValueError("Either start_location_name or start_coords must be provided.")
        if not end_name and not end_coords:
            raise ValueError("Either end_location_name or end_coords must be provided.")
        return values

# --- Helper Function: Geocode place name to coordinates ---
def geocode_location(location_name: str) -> Optional[Coordinates]:
    """Uses OpenRouteService Geocoding to find coordinates for a location name."""
    if not ors_client:
        print("ORS client not available for geocoding.")
        return None
    try:
        geocode_result = ors_client.pelias_search(text=location_name, size=1)
        if geocode_result and geocode_result.get('features'):
            coords = geocode_result['features'][0]['geometry']['coordinates']
            # Result is [longitude, latitude]
            return Coordinates(longitude=coords[0], latitude=coords[1])
        else:
            print(f"Geocoding failed for: {location_name}")
            return None
    except exceptions.ApiError as e:
        print(f"ORS Geocoding API Error for '{location_name}': {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during geocoding for '{location_name}': {e}")
        return None

# --- Define the Tool ---
@tool(args_schema=DirectionsSchema)
def get_openrouteservice_directions(
    profile: str,
    start_location_name: Optional[str] = None,
    end_location_name: Optional[str] = None,
    start_coords: Optional[Coordinates] = None,
    end_coords: Optional[Coordinates] = None,
) -> str:
    """
    Calculates a route between two points using OpenRouteService.
    Provide either location names (e.g., 'Hotel XYZ, City') or coordinates.
    Returns the travel duration and distance.
    """
    if not ors_client:
        return "OpenRouteService API is not configured. Cannot get directions."

    # --- Geocode if names are provided and coordinates are missing ---
    if start_location_name and not start_coords:
        start_coords = geocode_location(start_location_name)
        if not start_coords:
            return f"Could not find coordinates for start location: {start_location_name}"

    if end_location_name and not end_coords:
        end_coords = geocode_location(end_location_name)
        if not end_coords:
            return f"Could not find coordinates for end location: {end_location_name}"

    # --- Prepare coordinates in the format ORS expects: (longitude, latitude) list ---
    coordinates = [
        (start_coords.longitude, start_coords.latitude),
        (end_coords.longitude, end_coords.latitude)
    ]

    print(f"DEBUG - Getting ORS directions. Profile: {profile}, Coords: {coordinates}")

    try:
        # Call the ORS Directions API
        routes = ors_client.directions(coordinates=coordinates, profile=profile, format='json')

        if not routes or 'routes' not in routes or not routes['routes']:
            return f"No route found between the specified locations for profile '{profile}'."

        # Extract summary info from the first route
        summary = routes['routes'][0].get('summary', {})
        duration_seconds = summary.get('duration', 0)
        distance_meters = summary.get('distance', 0)

        # Convert duration to minutes and distance to km/miles
        duration_minutes = round(duration_seconds / 60)
        distance_km = round(distance_meters / 1000, 1)
        # distance_miles = round(distance_km * 0.621371, 1) # Optional: include miles

        start_desc = start_location_name if start_location_name else f"Coords({start_coords.latitude:.4f}, {start_coords.longitude:.4f})"
        end_desc = end_location_name if end_location_name else f"Coords({end_coords.latitude:.4f}, {end_coords.longitude:.4f})"

        result = (
            f"Directions found from '{start_desc}' to '{end_desc}' using '{profile}':\n"
            f"- Estimated Duration: {duration_minutes} minutes\n"
            f"- Distance: {distance_km} km"
            # f" ({distance_miles} miles)" # Optional
        )
        print(f"DEBUG - ORS Directions Result: Duration={duration_minutes}min, Distance={distance_km}km")
        return result

    except exceptions.ApiError as e:
        # Handle specific ORS API errors
        error_body = e.args[0] if e.args else {}
        status_code = e.args[1] if len(e.args) > 1 else 'Unknown'
        message = error_body.get('error', {}).get('message', str(e)) if isinstance(error_body, dict) else str(e)
        print(f"❌ ORS Directions API Error ({status_code}): {message}")
        return f"OpenRouteService API Error: Could not get directions. ({message})"
    except ValueError as e: # Catch validation errors from Pydantic/ORS client
        print(f"❌ Input validation error for ORS: {e}")
        return f"Input Error: {str(e)}"
    except Exception as e:
        print(f"❌ An unexpected error occurred during directions search: {e}")
        import traceback
        traceback.print_exc()
        return f"An unexpected error occurred: {e}"

# Example Usage (for testing)
# if __name__ == "__main__":
#     # Make sure ORS_API_KEY is in your .env file
#     load_dotenv()
#     ORS_API_KEY = os.getenv("ORS_API_KEY")
#     if ORS_API_KEY:
#         ors_client = openrouteservice.Client(key=ORS_API_KEY)
#         print("Testing Directions Tool...")
#         # Test Case 1: Using names (requires geocoding)
#         result_names = get_openrouteservice_directions(
#              start_location_name="Eiffel Tower, Paris",
#              end_location_name="Louvre Museum, Paris",
#              profile="foot-walking"
#         )
#         print("\n--- Test Case 1 (Names) ---")
#         print(result_names)

#         # Test Case 2: Using coordinates
#         result_coords = get_openrouteservice_directions(
#              start_coords=Coordinates(longitude=2.2945, latitude=48.8584), # Eiffel Tower approx coords
#              end_coords=Coordinates(longitude=2.3376, latitude=48.8606),   # Louvre approx coords
#              profile="foot-walking"
#         )
#         print("\n--- Test Case 2 (Coords) ---")
#         print(result_coords)
#     else:
#         print("ORS_API_KEY not set. Cannot run tests.")
