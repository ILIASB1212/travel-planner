# Import necessary libraries
import os
from typing import Optional, Dict, Any
from amadeus import Client, ResponseError
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- Amadeus Client Initialization ---
# Assuming AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET are set in environment variables
# --- Amadeus Client Initialization ---
# Debug: Print what we're getting


try:
    amadeus_id = "Ui0TUONWs7Ln9f5H8pEV0HG6cApUld4M"
    amadeus_secret = "EvIoWaVGgXL73yGe"
    
    if not amadeus_id or not amadeus_secret:
        print("WARNING: Amadeus credentials not found in environment variables")
        amadeus = None
    else:
        amadeus = Client(
            client_id=amadeus_id,
            client_secret=amadeus_secret
        )
        print("✅ Amadeus client initialized successfully")
except Exception as e:
    print(f"❌ Amadeus Client Initialization failed: {e}")
    amadeus = None

# --- IATA to Airline Name Mapping (Common Airlines) ---
AIRLINE_NAMES = {
    'AA': 'American Airlines',
    'DL': 'Delta Air Lines',
    'UA': 'United Airlines',
    'BA': 'British Airways',
    'AF': 'Air France',
    'LH': 'Lufthansa',
    'EK': 'Emirates',
    'QR': 'Qatar Airways',
    'TK': 'Turkish Airlines',
    'SQ': 'Singapore Airlines',
    'CX': 'Cathay Pacific',
    'QF': 'Qantas',
    'AC': 'Air Canada',
    'NH': 'All Nippon Airways',
    'JL': 'Japan Airlines',
    'KL': 'KLM Royal Dutch Airlines',
    'IB': 'Iberia',
    'AZ': 'ITA Airways',
    'LX': 'Swiss International Air Lines',
    'OS': 'Austrian Airlines',
    'SK': 'SAS Scandinavian Airlines',
    'AY': 'Finnair',
    'EI': 'Aer Lingus',
    'TP': 'TAP Air Portugal',
    'AT': 'Royal Air Maroc',
    'MS': 'EgyptAir',
    'ET': 'Ethiopian Airlines',
    'SA': 'South African Airways',
    'KE': 'Korean Air',
    'OZ': 'Asiana Airlines',
    'CA': 'Air China',
    'MU': 'China Eastern Airlines',
    'CZ': 'China Southern Airlines',
    'TG': 'Thai Airways',
    'VN': 'Vietnam Airlines',
    'GA': 'Garuda Indonesia',
    'PR': 'Philippine Airlines',
    'MH': 'Malaysia Airlines',
    'BR': 'EVA Air',
    'CI': 'China Airlines',
    'AI': 'Air India',
    '9W': 'Jet Airways',
    '6E': 'IndiGo',
    'SV': 'Saudi Arabian Airlines',
    'GF': 'Gulf Air',
    'WY': 'Oman Air',
    'RJ': 'Royal Jordanian',
    'LA': 'LATAM Airlines',
    'AM': 'Aeroméxico',
    'AR': 'Aerolíneas Argentinas',
    'CM': 'Copa Airlines',
    'AV': 'Avianca',
    'VY': 'Vueling',
    'U2': 'easyJet',
    'FR': 'Ryanair',
    'W6': 'Wizz Air',
    'NK': 'Spirit Airlines',
    'F9': 'Frontier Airlines',
    'B6': 'JetBlue Airways',
    'WN': 'Southwest Airlines',
    'AS': 'Alaska Airlines',
}

def get_airline_name(iata_code: str) -> str:
    """Convert IATA airline code to full airline name."""
    return AIRLINE_NAMES.get(iata_code, iata_code)

# --- Define the Pydantic Schema for the LLM ---
class FlightSearchSchema(BaseModel):
    """Input parameters for searching the cheapest flight offers."""
    originLocationCode: str = Field(..., description="The IATA code of the departure airport (e.g., RBA for Rabat).")
    destinationLocationCode: str = Field(..., description="The IATA code of the arrival airport (e.g., BKK for Bangkok).")
    departureDate: str = Field(..., description="The exact departure date in YYYY-MM-DD format (e.g., 2025-11-01).")
    returnDate: Optional[str] = Field(None, description="The exact return date in YYYY-MM-DD format. Required for round trip.")
    adults: int = Field(1, description="The number of adult passengers.")
    
@tool(args_schema=FlightSearchSchema)
def amadeus_flight_search(
    originLocationCode: str,
    destinationLocationCode: str,
    departureDate: str,
    returnDate: Optional[str] = None,
    adults: int = 1
) -> str:
    """
    Searches Amadeus for the cheapest flight offers between two airports on specified dates.
    Returns the cheapest price and carrier/airline information.
    """
    if not amadeus:
        return "Amadeus API is not configured. Cannot search for flights."

    try:
        # Build the query parameters
        params = {
            'originLocationCode': originLocationCode,
            'destinationLocationCode': destinationLocationCode,
            'departureDate': departureDate,
            'adults': adults,
            'max': 5 # Limit results for speed in the test environment
        }
        if returnDate:
            params['returnDate'] = returnDate

        # Call the Flight Offers Search API
        response = amadeus.shopping.flight_offers_search.get(**params)
        
        # --- ENHANCED LOGIC: Find the Cheapest Offer and Extract ALL Carrier Info ---
        if response.data:
            # Initialize variables to track the best deal
            cheapest_price = float('inf')
            cheapest_carrier_codes = []
            cheapest_carrier_names = []
            validating_airline_codes = []
            currency = "" 
            
            for offer in response.data:
                # Use a try block in case price field is malformed
                try:
                    current_price = float(offer['price']['total'])
                    currency = offer['price']['currency']
                except (ValueError, KeyError):
                    continue # Skip this offer if price data is bad

                if current_price < cheapest_price:
                    cheapest_price = current_price
                    
                    # Extract ALL carrier information from this offer
                    # 1. Validating airline codes (ticket issuer)
                    validating_airline_codes = offer.get('validatingAirlineCodes', [])
                    
                    # 2. Extract carriers from itineraries (actual operating airlines)
                    carrier_codes_set = set()
                    itineraries = offer.get('itineraries', [])
                    for itinerary in itineraries:
                        segments = itinerary.get('segments', [])
                        for segment in segments:
                            # Get both operating and marketing carriers
                            if 'carrierCode' in segment:
                                carrier_codes_set.add(segment['carrierCode'])
                            if 'operating' in segment and 'carrierCode' in segment['operating']:
                                carrier_codes_set.add(segment['operating']['carrierCode'])
                    
                    cheapest_carrier_codes = list(carrier_codes_set)
                    
                    # Convert IATA codes to airline names
                    cheapest_carrier_names = [get_airline_name(code) for code in cheapest_carrier_codes]
                    validating_airline_names = [get_airline_name(code) for code in validating_airline_codes]
            
            # --- FINAL RETURN STATEMENT (outside the loop) ---
            if cheapest_price != float('inf'):
                # Build a detailed response with all carrier information
                result_parts = [
                    f"Cheapest flight price found: {cheapest_price:.2f} {currency}"
                ]
                
                # Add ticket provider (validating airline)
                if validating_airline_names:
                    result_parts.append(f"Ticket Provider/Validating Airline: {', '.join(validating_airline_names)} ({', '.join(validating_airline_codes)})")
                
                # Add operating airlines
                if cheapest_carrier_names:
                    result_parts.append(f"Operating Airline(s): {', '.join(cheapest_carrier_names)} ({', '.join(cheapest_carrier_codes)})")
                
                result_parts.append("Note: This is a test environment result and prices are not guaranteed.")
                
                return " | ".join(result_parts)
            else:
                return "No flight offers found for this itinerary."

        else:
            return "No flight offers found for this itinerary."

    except ResponseError as e:
        return f"Amadeus API Error: Could not complete search. Check your IATA codes and dates. Details: {e.code} - {e.description}"
    except Exception as e:
        return f"An unexpected error occurred during the flight search: {e}"