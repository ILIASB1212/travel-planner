from langchain_google_community import GoogleSearchAPIWrapper
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional

api_key="AIzaSyBfbJVw4qNoxmNgWkmFii4isTCERsrtiKY"
cse_id="97b82ecacffd94443"
#google_api_key=api_key,google_cse_id=cse_id
import os
#os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
#os.environ["GOOGLE_SCE_ID"]=os.getenv("GOOGLE_SCE_ID")
try:
    # --- MODIFICATION: The new wrapper reads keys from environment by default ---
    google_search = GoogleSearchAPIWrapper(google_api_key=api_key,google_cse_id=cse_id)
except ImportError:
    print("Could not import GoogleSearchAPIWrapper. Please install langchain-google-community: pip install -U langchain-google-community")
    google_search = None
except Exception as e:
    print(f"Could not initialize GoogleSearchAPIWrapper: {e}")
    google_search = None

# --- Tool 1: Local Travel Activities ---

class ActivitySearchSchema(BaseModel):
    """Input parameters for searching for local activities."""
    destination: str = Field(..., description="The city or country to search for activities (e.g., 'Marrakech', 'Morocco').")
    interests: str = Field(..., description="User's interests for activities (e.g., 'history, food', 'hiking, museums', 'beach, nightlife').")

@tool(args_schema=ActivitySearchSchema)
def google_search_activities(destination: str, interests: str) -> str:
    """
    Searches Google for activities, tours, and points of interest for a user.
    Use this to find things to do at a travel destination based on the user's interests.
    """
    if not google_search:
        return "Google Search is not configured."

    query = f"top activities and attractions in {destination} for {interests}"
    print(f"DEBUG - Searching activities with query: {query}")
    
    try:
        results = google_search.run(query)
        if not results:
            return f"No activities found for '{query}'. Try a broader search."
            
        return f"Activity search results for '{query}':\n\n{results}"
    except Exception as e:
        return f"Error during Google search: {str(e)}"

# --- Tool 2: Series & Movie Recommendations ---

class EntertainmentSearchSchema(BaseModel):
    """Input parameters for searching for series or movies."""
    genre: str = Field(..., description="The genre of the series or movie (e.g., 'sci-fi', 'comedy', 'thriller').")
    search_type: str = Field(..., description="The type of entertainment to search for. Must be 'series' or 'movies'.")
    keywords: Optional[str] = Field(None, description="Optional keywords to refine the search (e.g., 'space exploration', '90s').")

@tool(args_schema=EntertainmentSearchSchema)
def google_search_entertainment(genre: str, search_type: str, keywords: Optional[str] = None) -> str:
    """
    Searches Google for series or movie recommendations based on genre and keywords.
    """
    if not google_search:
        return "Google Search is not configured."

    # Validate search_type
    if search_type.lower() not in ['series', 'movies']:
        return "Error: search_type must be 'series' or 'movies'."
        
    query_parts = [
        "best",
        genre,
        search_type
    ]
    if keywords:
        query_parts.append(f"about {keywords}")
        
    query = " ".join(query_parts)
    print(f"DEBUG - Searching entertainment with query: {query}")
    
    try:
        results = google_search.run(query)
        if not results:
            return f"No recommendations found for '{query}'."
            
        return f"Entertainment recommendations for '{query}':\n\n{results}"
    except Exception as e:
        return f"Error during Google search: {str(e)}"

