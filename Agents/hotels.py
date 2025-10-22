# Import necessary libraries
import os
import requests
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- SearchApi Configuration ---
SEARCHAPI_KEY = os.getenv("SEARCHAPI_KEY")
SEARCHAPI_BASE_URL = "https://www.searchapi.io/api/v1/search"

# --- Define the Pydantic Schema for Hotel Search ---
class HotelSearchSchema(BaseModel):
    """Input parameters for searching hotels using SearchApi (Google Hotels)."""
    query: str = Field(..., description="Hotel search query including destination (e.g., 'hotels in Bangkok', 'hotels near Eiffel Tower Paris').")
    checkin_date: str = Field(..., description="Check-in date in YYYY-MM-DD format (e.g., 2025-11-01).")
    checkout_date: str = Field(..., description="Check-out date in YYYY-MM-DD format (e.g., 2025-11-05).")
    adults: int = Field(2, description="Number of adult guests.")
    children: int = Field(0, description="Number of children.")
    currency: str = Field("USD", description="Preferred currency code (e.g., USD, EUR, MAD).")
    gl: str = Field("us", description="Country code for Google domain (e.g., us, ma, fr).")
    hl: str = Field("en", description="Language code (e.g., en, fr, ar).")
    sort_by: str = Field("3", description="Sort order: 3=lowest price, 13=highest rating, 8=most reviewed.")


@tool(args_schema=HotelSearchSchema)
def searchapi_hotel_search(
    query: str,
    checkin_date: str,
    checkout_date: str,
    adults: int = 2,
    children: int = 0,
    currency: str = "USD",
    gl: str = "us",
    hl: str = "en",
    sort_by: str = "3"
) -> str:
    """
    Search for hotels using SearchApi.io (Google Hotels data).
    Returns a list of hotels with names, prices, ratings, and booking links.
    """
    if not SEARCHAPI_KEY:
        return "SearchApi is not configured. Please set SEARCHAPI_KEY environment variable."

    try:
        # Build search parameters
        params = {
            "engine": "google_hotels",
            "q": f"hotels in {query}",
            "check_in_date": checkin_date,
            "check_out_date": checkout_date,
            "adults": adults,
            "currency": currency,
            "gl": gl,
            "hl": hl,
            "sort_by": sort_by,
            "api_key": SEARCHAPI_KEY
        }
        
        if children > 0:
            params["children"] = children

        # Make API request
        response = requests.get(SEARCHAPI_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract hotel properties
        properties = data.get("properties", [])
        
        if not properties:
            return f"No hotels found for '{query}' on the specified dates. Try adjusting your search criteria."
        
        # Process and format hotel results
        hotel_results = []
        
        for idx, hotel in enumerate(properties[:10], 1):  # Top 10 results
            # Extract hotel information
            name = hotel.get("name", "Unknown Hotel")
            
            # Get pricing
            rate_per_night = hotel.get("rate_per_night", {})
            lowest_price = rate_per_night.get("lowest", "N/A")
            price_currency = rate_per_night.get("currency", currency)
            
            # Calculate total price (nights * rate)
            total_price = hotel.get("total_rate", {}).get("lowest", "N/A")
            
            # Get ratings
            overall_rating = hotel.get("overall_rating", "N/A")
            reviews = hotel.get("reviews", 0)
            
            # Get hotel type/description
            hotel_type = hotel.get("type", "Hotel")
            
            # Get location details
            gps_coordinates = hotel.get("gps_coordinates", {})
            latitude = gps_coordinates.get("latitude", "")
            longitude = gps_coordinates.get("longitude", "")
            
            # Get check-in/check-out times
            check_in_time = hotel.get("check_in_time", "")
            check_out_time = hotel.get("check_out_time", "")
            
            # Get nearby places (if available)
            nearby_places = hotel.get("nearby_places", [])
            nearby_info = ""
            if nearby_places:
                nearby_info = f" | Near: {nearby_places[0].get('name', '')}" if len(nearby_places) > 0 else ""
            
            # Get images
            images = hotel.get("images", [])
            main_image = images[0].get("thumbnail") if images else "No image"
            
            # Get amenities
            amenities = hotel.get("amenities", [])
            amenity_list = ", ".join(amenities[:5]) if amenities else "Not listed"
            
            # Get booking link (if available)
            link = hotel.get("link", "")
            
            # Format hotel information
            hotel_info = (
                f"{idx}. {name}\n"
                f"   Type: {hotel_type}\n"
                f"   Price: {lowest_price} {price_currency}/night"
            )
            
            if total_price != "N/A":
                hotel_info += f" | Total: {total_price} {price_currency}"
            
            hotel_info += (
                f"\n   Rating: {overall_rating}/5 ({reviews} reviews)\n"
                f"   Amenities: {amenity_list}"
            )
            
            if check_in_time:
                hotel_info += f"\n   Check-in: {check_in_time}"
            if check_out_time:
                hotel_info += f" | Check-out: {check_out_time}"
            
            if nearby_info:
                hotel_info += f"\n   {nearby_info}"
            
            if link:
                hotel_info += f"\n   Booking Link: {link}"
            
            hotel_results.append(hotel_info)
        
        # Build final response
        search_info = data.get("search_parameters", {})
        result_summary = (
            f"🏨 Hotel Search Results for '{query}'\n"
            f"📅 {checkin_date} to {checkout_date} | 👥 {adults} adult(s)"
        )
        
        if children > 0:
            result_summary += f", {children} child(ren)"
        
        result_summary += f"\n💰 Sorted by: {'Lowest Price' if sort_by == '3' else 'Best Match'}\n"
        result_summary += f"\nFound {len(properties)} hotels. Showing top {len(hotel_results)}:\n\n"
        result_summary += "\n\n".join(hotel_results)
        result_summary += "\n\n✅ Prices include taxes and fees. Click booking links for more details and to reserve."
        
        return result_summary

    except requests.exceptions.RequestException as e:
        return f"API request failed: {str(e)}"
    except Exception as e:
        return f"An error occurred during hotel search: {str(e)}"


# --- Additional Tool: Quick Hotel Lookup by Destination ---
class QuickHotelSearchSchema(BaseModel):
    """Simplified hotel search with just destination and dates."""
    destination: str = Field(..., description="Destination city or area (e.g., 'Bangkok', 'Paris', 'New York').")
    checkin_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    checkout_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")
    adults: int = Field(2, description="Number of adult guests.")
    budget_max: Optional[int] = Field(None, description="Maximum budget per night in USD (optional filter).")


@tool(args_schema=QuickHotelSearchSchema)
def quick_hotel_search(
    destination: str,
    checkin_date: str,
    checkout_date: str,
    adults: int = 2,
    budget_max: Optional[int] = None
) -> str:
    """
    Quick hotel search by destination name. Automatically formats query and returns budget-friendly options.
    """
    # Format the query for Google Hotels
    query = f"hotels in {destination}"
    
    # Use the main search tool
    result = searchapi_hotel_search(
        query=query,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        adults=adults,
        currency="USD",
        gl="us",
        hl="en",
        sort_by="3"  # Sort by lowest price
    )
    
    # If budget filter is specified, add a note
    if budget_max:
        result += f"\n\n💡 Budget Filter: Looking for hotels under ${budget_max}/night. Review the prices above."
    
    return result


# --- Tool: Get Hotel Details by Hotel ID ---
class HotelDetailsSchema(BaseModel):
    """Get detailed information about a specific hotel."""
    hotel_id: str = Field(..., description="The Google Hotels property ID.")
    checkin_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    checkout_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")
    adults: int = Field(2, description="Number of adult guests.")
    currency: str = Field("USD", description="Preferred currency code.")


@tool(args_schema=HotelDetailsSchema)
def searchapi_hotel_details(
    hotel_id: str,
    checkin_date: str,
    checkout_date: str,
    adults: int = 2,
    currency: str = "USD"
) -> str:
    """
    Get detailed information about a specific hotel including all room types and rates.
    """
    if not SEARCHAPI_KEY:
        return "SearchApi is not configured. Please set SEARCHAPI_KEY environment variable."

    try:
        params = {
            "engine": "google_hotels",
            "hotel_id": hotel_id,
            "check_in_date": checkin_date,
            "check_out_date": checkout_date,
            "adults": adults,
            "currency": currency,
            "api_key": SEARCHAPI_KEY
        }

        response = requests.get(SEARCHAPI_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract hotel details
        hotel_name = data.get("name", "Unknown Hotel")
        description = data.get("description", "No description available")
        overall_rating = data.get("overall_rating", "N/A")
        reviews = data.get("reviews", 0)
        
        # Get amenities
        amenities = data.get("amenities", [])
        amenities_text = ", ".join(amenities) if amenities else "Not listed"
        
        # Get room rates
        prices = data.get("prices", [])
        
        result = (
            f"🏨 {hotel_name}\n"
            f"⭐ Rating: {overall_rating}/5 ({reviews} reviews)\n"
            f"📝 {description}\n\n"
            f"🛎️ Amenities: {amenities_text}\n\n"
        )
        
        if prices:
            result += "💰 Available Rates:\n\n"
            for idx, price_option in enumerate(prices[:5], 1):
                source = price_option.get("source", "Provider")
                rate = price_option.get("rate", "N/A")
                total = price_option.get("total", "N/A")
                link = price_option.get("link", "")
                
                result += f"{idx}. {source}: {rate} {currency}/night | Total: {total} {currency}\n"
                if link:
                    result += f"   Book: {link}\n"
        else:
            result += "No rates available for the selected dates.\n"
        
        return result

    except Exception as e:
        return f"Error fetching hotel details: {str(e)}"