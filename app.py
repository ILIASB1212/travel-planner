
from Agents.hotels import searchapi_hotel_search, searchapi_hotel_details, quick_hotel_search
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from typing import Annotated, TypedDict, List, Optional
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from Agents.flight import amadeus_flight_search
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from Agents.activities import google_search_activities 
from Agents.directions import get_openrouteservice_directions # <-- ADDED
import streamlit as st
import json
import uuid
import os
import sqlite3
import re

#-----API KEYS SETUP-----
load_dotenv()
# Make sure ORS_API_KEY is loaded for directions.py
os.environ["ORS_API_KEY"] = os.getenv("ORS_API_KEY")
# --- MODIFICATION: Removed redundant os.environ lines for other keys ---
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "travel-planner"
# --- END OF MODIFICATION ---

#------llm setup------
llm = ChatOpenAI(model_name="gpt-4o-mini")

#------- base model initaliser----------
class Travel(BaseModel):
    depart: Optional[str] = Field(None, description="The place the user will start from")
    destination: Optional[str] = Field(None, description="The destination the user wants to go")
    duration: Optional[str] = Field(None, description="The duration of the travel (e.g., '4 days', '7 days')")
    adults: Optional[int] = Field(2, description="The number of adult travelers.")
    budget: Optional[str] = Field(None, description="User budget to spend (e.g., '3000 USD')")
    departureDate: Optional[str] = Field(None, description="The exact departure date in YYYY-MM-DD format (e.g., 2025-11-01).")
    returnDate: Optional[str] = Field(None, description="The exact return date in YYYY-MM-DD format (e.g., 2025-11-06).")
    interests: Optional[str] = Field(None, description="User's interests for activities (e.g., 'history, food', 'hiking, museums', 'beach, nightlife').")
    # --- ADDITION: Ask if directions are needed ---
    needs_directions: Optional[bool] = Field(False, description="Set to true if the user explicitly asks for directions between places mentioned in the plan (e.g., 'hotel to museum').")

# Tools for LLM awareness
tools = [
    amadeus_flight_search,
    quick_hotel_search,
    google_search_activities,
    get_openrouteservice_directions, # <-- ADDED
    Travel
]

# Execution tools
excecution_tool = [
    amadeus_flight_search,
    quick_hotel_search,
    google_search_activities,
    get_openrouteservice_directions # <-- ADDED
]

llm_with_tools = llm.bind_tools(tools)

#-----TYPED DICTS-----
class State(TypedDict):
    depart: Optional[str]
    destination: str
    duration: str
    adults: int
    budget: str
    departureDate: Optional[str]
    returnDate: Optional[str]
    interests: Optional[str]
    needs_directions: bool
    flight_cost_eur: Optional[float]
    flight_carrier: Optional[str]
    hotel_searched: bool
    flight_searched: bool
    activities_searched: bool
    directions_searched: bool 
    feasibility_status: Optional[str]
    remaining_budget_usd: Optional[float]
    messages: Annotated[list, add_messages]

#----------NODES-----------
def chatbot(state: State):
    context = ""
    relevant_state = {k: v for k, v in state.items() if k not in ['messages', 'feasibility_status', 'remaining_budget_usd', 'flight_cost_eur', 'hotel_searched', 'flight_searched', 'activities_searched', 'directions_searched'] and v and v != [''] and v != ''}

    if relevant_state:
        context = "Current Travel Plan Details:\n"
        for k, v in relevant_state.items():
            if k != 'needs_directions':
                 context += f"- {k.replace('_', ' ').title()}: {v}\n"

    budget = state.get('budget', 'the provided budget')
    destination = state.get('destination', 'the chosen destination')
    duration = state.get('duration', 'the specified number of')
    feasibility_status = state.get('feasibility_status', 'UNKNOWN')

    flight_searched = state.get('flight_searched', False) or any(
        hasattr(m, 'name') and m.name == 'amadeus_flight_search'
        for m in state['messages']
    )
    hotel_searched = state.get('hotel_searched', False) or any(
        hasattr(m, 'name') and m.name == 'quick_hotel_search'
        for m in state['messages']
    )
    activities_searched = state.get('activities_searched', False) or any(
        hasattr(m, 'name') and m.name == 'google_search_activities'
        for m in state['messages']
    )
    needs_directions_flag = state.get('needs_directions', False)
    directions_searched = state.get('directions_searched', False) or any(
         hasattr(m, 'name') and m.name == 'get_openrouteservice_directions'
         for m in state['messages']
    )
    
    if flight_searched and hotel_searched and activities_searched:

        if needs_directions_flag and not directions_searched:
            print("✅ chatbot: All searches done, proceeding to directions search")

            prompt_instructions = [
                "You are an expert travel planner.",
                "The user needs directions between two locations from the plan.",
                "Here is the data you must use for the tool call (including hotel/activity names from previous steps in message history):",
                context,
                f"\nCURRENT STATUS:\n- Flight Searched: {flight_searched}\n- Hotel Searched: {hotel_searched}\n- Activities Searched: {activities_searched}\n- Directions Searched: {directions_searched}\n",
                "Task: Get directions.",
                "Tool to use: 'get_openrouteservice_directions'.",
                "You need to infer the start_location_name and end_location_name from the user request and message history.",
                "Be specific with names and include the city (e.g., Start='Hotel Le Djoloff, Dakar', End='IFAN Museum of African Arts, Dakar').",
                "Choose a suitable profile (e.g., 'foot-walking' or 'driving-car').",
                "DO NOT use any other tool.",
                "\n\n⚠️ CRITICAL: Only call 'get_openrouteservice_directions' NOW."
            ]
            system_prompt = "\n".join(prompt_instructions)
            messages_for_llm = [SystemMessage(content=system_prompt)] + state['messages']
            result = llm_with_tools.invoke(messages_for_llm)

        else:
            print("✅ chatbot: Generating FINAL response (using base llm)")

            system_prompt = f"""You are an expert travel planner providing the FINAL travel plan summary.

IMPORTANT: You must not call any tools. You already have all the information needed.

You have received:
- User interests
- Flight search results
- Hotel search results
- Activity search results
- (Potentially) Directions results
(All this information is in the message history)

Your task now is to provide a comprehensive final response including:

1.  **Trip Summary** (Destination, Duration, Budget, Interests, Status)
2.  **Flight Details** (Carrier, Price in EUR, Price in USD using 1 EUR = 1.07 USD)
3.  **Hotel Recommendations** (Top 2-3 with Name, Price, Rating)
4.  **Activity Recommendations** (Summarize search, suggest 2-3 specific activities)
5.  **Local Transportation/Directions** (IF available in message history from 'get_openrouteservice_directions' tool, summarize the duration and distance. If not, omit this section.)
6.  **Budget Breakdown** (Flight USD, Hotel USD, Remaining USD)
7.  **Recommendations** (Feasibility, Suggestions)

{context}

Provide a well-formatted, conversational response. DO NOT call any tools."""

            messages_with_context = [SystemMessage(content=system_prompt)] + state['messages']
            result = llm.invoke(messages_with_context)

    else:
        
        print(f"✅ chatbot: Running normal workflow (flight: {flight_searched}, hotel: {hotel_searched}, activities: {activities_searched})")

        prompt_instructions = [
            "You are a travel planning assistant. Your ONLY job is to determine the SINGLE NEXT tool to call based on the explicit instructions below.",
            "DO NOT DEVIATE. DO NOT CALL PREVIOUS TOOLS.",
            "\nData available for tool call:",
            context,
            f"\nCURRENT SEARCH STATUS:\n- Flight Searched: {flight_searched}\n- Hotel Searched: {hotel_searched}\n- Activities Searched: {activities_searched}\n- Budget Status: {feasibility_status}\n"
        ]

        # --- Stricter Logic ---
        if not state.get('destination'):
            prompt_instructions.append("Instruction: User details are missing. Call ONLY the 'Travel' tool to get them.")
            tool_to_call = "Travel"
        elif not flight_searched:
            prompt_instructions.append("Instruction: Flight search is needed. Call ONLY the 'amadeus_flight_search' tool using the data provided.")
            tool_to_call = "amadeus_flight_search"
        elif not hotel_searched:
            prompt_instructions.append("Instruction: Hotel search is needed. Flight search is COMPLETE.")
            prompt_instructions.append("Call ONLY the 'quick_hotel_search' tool using the data provided.")
            prompt_instructions.append("DO NOT call 'amadeus_flight_search' again.")
            tool_to_call = "quick_hotel_search"
        elif not activities_searched:
            prompt_instructions.append("Instruction: Activity search is needed. Flight and Hotel searches are COMPLETE.")
            prompt_instructions.append("Call ONLY the 'google_search_activities' tool using the data provided.")
            prompt_instructions.append("DO NOT call 'amadeus_flight_search' or 'quick_hotel_search' again.")
            tool_to_call = "google_search_activities"
        else:
             prompt_instructions.append("Instruction: All standard searches are complete. DO NOT call any tools now.")
             tool_to_call = None 

        prompt_instructions.append(f"\nYour response MUST be a call to the tool '{tool_to_call}' if specified, otherwise no tool call.")
        prompt_instructions.append("Provide ONLY the tool call, no other text.")

        system_prompt = "\n".join(prompt_instructions)
        messages_for_llm = [SystemMessage(content=system_prompt)]
        if tool_to_call == "Travel": 
            for msg in reversed(state['messages']):
                if isinstance(msg, HumanMessage):
                    messages_for_llm.append(msg)
                    break

        result = llm_with_tools.invoke(messages_for_llm)


    print(f"DEBUG - LLM Response tool_calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")
    print(f"DEBUG - LLM Response content length: {len(result.content) if result.content else 0}")

    return {"messages": [result]}

def update_state(state: State):
    """Extract travel data from the AI message that called the Travel tool."""
    ai_messages = [m for m in state['messages'] if hasattr(m, 'tool_calls') and m.tool_calls]
    if not ai_messages: return {}

    for ai_msg in reversed(ai_messages):
        for tool_call in ai_msg.tool_calls:
            if tool_call['name'] == 'Travel':
                try:
                    extracted_data = tool_call['args']
                    new_state = {}

                    field_mapping = {
                        'depart': 'depart', 'destination': 'destination', 'duration': 'duration',
                        'adults': 'adults', 'budget': 'budget', 'departureDate': 'departureDate',
                        'returnDate': 'returnDate', 'interests': 'interests',
                        'needs_directions': 'needs_directions' # <-- ADDED
                    }

                    for source_key, target_key in field_mapping.items():
                        if source_key in extracted_data:
                            value = extracted_data[source_key]
                            if value is not None and value != '':
                                if target_key == 'adults': new_state[target_key] = int(value) if value else 1
                                elif target_key == 'needs_directions':
                                    if isinstance(value, str):
                                        new_state[target_key] = value.lower() == 'true'
                                    else:
                                        new_state[target_key] = bool(value)
                                else: new_state[target_key] = str(value)

                    if 'adults' not in new_state: new_state['adults'] = 1
                    if 'interests' not in new_state: new_state['interests'] = 'general sightseeing'
                    if 'needs_directions' not in new_state: new_state['needs_directions'] = False # Default to false

                    if 'duration' not in new_state and 'departureDate' in new_state and 'returnDate' in new_state:
                        from datetime import datetime
                        try:
                            dep = datetime.strptime(new_state['departureDate'], '%Y-%m-%d')
                            ret = datetime.strptime(new_state['returnDate'], '%Y-%m-%d')
                            days = (ret - dep).days
                            if days > 0: new_state['duration'] = f"{days} days"
                            else: new_state['duration'] = "Invalid dates"
                        except:
                            new_state['duration'] = "Date parse error"
                    elif 'duration' not in new_state and 'departureDate' in new_state:
                        new_state['duration'] = "Flexible / One-way" 
                    elif 'duration' not in new_state:
                        new_state['duration'] = "Not specified" 


                    print(f"✅ State extracted successfully: {new_state}")
                    return new_state

                except Exception as e:
                    print(f"❌ Error extracting Travel data: {e}")
                    import traceback; traceback.print_exc()
                    return {}
    return {}

def calculate_budget_status(state: State) -> dict:
    flight_messages = [m for m in state['messages'] if hasattr(m, 'name') and m.name == 'amadeus_flight_search']
    if not flight_messages: return {"feasibility_status": "ERROR", "flight_cost_eur": 0.0, "flight_carrier": "Unknown", "remaining_budget_usd": 0.0, "flight_searched": True}
    last_flight = flight_messages[-1]
    if "not configured" in last_flight.content or "API Error" in last_flight.content:
        print(f"Flight search failed: {last_flight.content}"); return {"feasibility_status": "ERROR", "flight_cost_eur": 0.0, "flight_carrier": "Unknown", "remaining_budget_usd": 0.0, "flight_searched": True}
    try:
        price_match = re.search(r'(\d+\.?\d*)\s*([A-Z]{3})', last_flight.content)
        flight_price_eur = 0.0
        currency = "EUR" 
        if price_match:
            flight_price_eur = float(price_match.group(1))
            currency = price_match.group(2) # Get actual currency if found

        carrier_match = re.search(r'(?:Operating Airline\(s\)|Validating Airline):\s*([^(\n|]+)', last_flight.content)
        flight_carrier = carrier_match.group(1).strip() if carrier_match else "Unknown"

        EUR_TO_USD_RATE = 1.07
        flight_price_usd = flight_price_eur * EUR_TO_USD_RATE if currency == "EUR" else flight_price_eur

    except Exception as e: print(f"Error parsing flight tool output: {e}"); return {"feasibility_status": "ERROR", "flight_cost_eur": 0.0, "flight_carrier": "Unknown", "remaining_budget_usd": 0.0, "flight_searched": True}
    try:
        budget_str = state.get('budget', '0 USD') 
        budget_match = re.search(r'(\d+)', budget_str)
        user_budget_usd = float(budget_match.group(0)) if budget_match else 0.0
    except Exception: user_budget_usd = 0.0
    MIN_GROUND_COSTS_USD = 300.0 
    remaining = user_budget_usd - flight_price_usd
    status = "FEASIBLE" if remaining >= MIN_GROUND_COSTS_USD else "OVER_BUDGET"
    print(f"💰 Budget Check: Flight={flight_price_usd:.2f} USD ({flight_price_eur:.2f} {currency}), Total Budget={user_budget_usd:.2f} USD, Remaining={remaining:.2f} USD, Status={status}")
    return {"flight_cost_eur": flight_price_eur, "flight_carrier": flight_carrier, "feasibility_status": status, "remaining_budget_usd": remaining, "flight_searched": True}


def route_after_tool_result(state: State) -> str:
    """Route based on the LAST tool that was executed."""
    tool_messages = [m for m in state['messages'] if hasattr(m, 'name')]
    if not tool_messages: return "chatbot"
    last_tool = tool_messages[-1]
    print(f"📍 Routing after tool: {last_tool.name}")

    if last_tool.name == "Travel": return "extract_data"
    elif last_tool.name == "amadeus_flight_search": return "budget_check"
    elif last_tool.name == "quick_hotel_search": return "mark_hotel_done"
    elif last_tool.name == "google_search_activities": return "mark_activities_done"
    elif last_tool.name == "get_openrouteservice_directions": return "mark_directions_done" # <-- ADDED
    return "chatbot"

def mark_hotel_complete(state: State) -> dict:
    """Mark hotel search as complete."""
    print("✅ Hotel search completed - preparing for activity search")
    return {"hotel_searched": True}

def mark_activities_complete(state: State) -> dict:
    """Mark activity search as complete."""
    print("✅ Activity search completed - checking if directions needed")
    return {"activities_searched": True}

def mark_directions_done(state: State) -> dict:
    """Mark directions search as complete."""
    print("✅ Directions search completed - preparing final response")
    return {"directions_searched": True}

def route_by_feasibility(state: State) -> str:
    status = state.get('feasibility_status'); print(f"🔀 Feasibility routing: {status}")
    return "chatbot"

def tools_condition(state: State) -> str:
    """Check if LLM wants to call tools or end."""
    last_message = state['messages'][-1]

    has_flight = state.get('flight_searched', False)
    has_hotel = state.get('hotel_searched', False)
    has_activities = state.get('activities_searched', False)
    needs_directions = state.get('needs_directions', False)
    has_directions = state.get('directions_searched', False)

    all_standard_searches_done = has_flight and has_hotel and has_activities
    directions_logic_complete = (not needs_directions) or (needs_directions and has_directions)

    if all_standard_searches_done and directions_logic_complete:
        print("✅ All required searches complete - deciding final step")
    
        if hasattr(last_message, 'content') and last_message.content and not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
            print("➡️ Final content found. Ending.")
            return END
        
        else:
             print("⚠️ Last message not final content or tried tool call. Routing to chatbot for summary.")
             if hasattr(last_message, 'tool_calls'):
                 last_message.tool_calls = []
             return "chatbot" # Force chatbot to generate final summary

    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        if len(last_message.tool_calls) > 1:
            print(f"⚠️ WARNING: Multiple tool calls detected, only executing first one")
            last_message.tool_calls = [last_message.tool_calls[0]]
        return "tools"

    print("⚠️ tools_condition: No tool calls but not finished? Routing to chatbot.")
    return "chatbot"


# Build graph
graph_builder = StateGraph(State)

graph_builder.add_node("chatbot", chatbot)
tool_node = ToolNode(tools=excecution_tool) 

def debug_tool_node(state: State):
    last_msg = state['messages'][-1]
    tool_calls = getattr(last_msg, 'tool_calls', [])
    print(f"\n🔧 DEBUG - Executing tools: {tool_calls}")

    if tool_calls and len(tool_calls) > 1:
        print(f"⚠️ Limiting to first tool call only")
        mutable_calls = list(tool_calls) 
        last_msg.tool_calls = [mutable_calls[0]] 
    if not tool_calls:
         print("⚠️ debug_tool_node: No tool calls found in last message.")
         return {"messages": [ToolMessage(content="No tool to execute.", tool_call_id="N/A")]}


    try:
        result = tool_node.invoke(state)
        print(f"   Tool results: {[getattr(msg, 'name', 'N/A') for msg in result.get('messages', []) if isinstance(msg, ToolMessage) or hasattr(msg, 'name')]}")
        if isinstance(result, dict):
            return result
        elif isinstance(result, list): 
             return {"messages": result}
        else:
            print(f"⚠️ Unexpected tool node result type: {type(result)}")
            if hasattr(result, '__iter__'):
                 return {"messages": list(result)}
            else: 
                 error_msg = ToolMessage(content=f"Unexpected tool result type: {type(result)}", tool_call_id=tool_calls[0]['id'] if tool_calls else 'N/A')
                 current_messages = state.get('messages', [])
                 return {"messages": current_messages + [error_msg]}

    except Exception as e:
        print(f"❌ Error during tool execution: {e}")
        import traceback
        traceback.print_exc() 
        error_message = ToolMessage(content=f"Error executing tool: {e}", tool_call_id=tool_calls[0]['id'] if tool_calls else 'N/A')
        current_messages = state.get('messages', [])
        return {"messages": current_messages + [error_message]}


graph_builder.add_node("tools", debug_tool_node)
graph_builder.add_node("extract_data", update_state)
graph_builder.add_node("budget_check", calculate_budget_status)
graph_builder.add_node("mark_hotel_done", mark_hotel_complete)
graph_builder.add_node("mark_activities_done", mark_activities_complete)
graph_builder.add_node("mark_directions_done", mark_directions_done)

graph_builder.add_edge(START, "chatbot")

graph_builder.add_conditional_edges("chatbot", tools_condition, {
    "tools": "tools",
    "chatbot": "chatbot",
    END: END
})

graph_builder.add_conditional_edges("tools", route_after_tool_result, {
    "extract_data": "extract_data",
    "budget_check": "budget_check",
    "mark_hotel_done": "mark_hotel_done",
    "mark_activities_done": "mark_activities_done",
    "mark_directions_done": "mark_directions_done", 
    "chatbot": "chatbot"
})

graph_builder.add_edge("extract_data", "chatbot")
graph_builder.add_conditional_edges("budget_check", route_by_feasibility, {"chatbot": "chatbot"})
graph_builder.add_edge("mark_hotel_done", "chatbot")
graph_builder.add_edge("mark_activities_done", "chatbot")
graph_builder.add_edge("mark_directions_done", "chatbot")



db_directory = "database"
if not os.path.exists(db_directory):
    os.makedirs(db_directory)
db_path = os.path.join(db_directory, "memory.db")


conn = None 
try:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn=conn)
    graph = graph_builder.compile(checkpointer=memory)
    print("✅ Graph compiled with SQLite checkpointer.")
except Exception as e:
    print(f"❌ Failed to compile graph with checkpointer: {e}")
    graph = graph_builder.compile() 
    print("⚠️ WARNING: Graph compiled WITHOUT checkpointer due to error.")
    if conn: 
        try: conn.close()
        except: pass
        conn = None 
# --- END OF MODIFICATION ---

#--------------------UI------------------------
st.title("🌍 Travel Planner")

if st.button("🔄 New Conversation"):
    # Clear thread_id from session state to start fresh
    st.session_state.thread_id = None
    st.rerun() # Rerun clears messages implicitly

# Manage thread_id for memory
if "thread_id" not in st.session_state or st.session_state.thread_id is None:
    st.session_state.thread_id = str(uuid.uuid4())
    print(f"Starting new thread: {st.session_state.thread_id}") # Debug new thread

config = {"configurable": {"thread_id": st.session_state.thread_id}}


# Added interests and directions to placeholder
user_input = st.text_area("Enter travel request (e.g., '5 days Morocco $2000, history/food, directions hotel to museum?'):", height=100)

if st.button("✈️ Plan My Trip"):
    if user_input:
        with st.spinner("Planning your trip... This may take several steps..."):
            try:
                initial_messages = [HumanMessage(content=user_input)]

                # Pass config to invoke
                response = graph.invoke({'messages': initial_messages}, config=config)

                print(f"\n{'='*50}\nFINAL RESPONSE DEBUG\n{'='*50}")
                print(f"Total messages: {len(response['messages'])}")

                final_response = None
                for msg in reversed(response["messages"]):
                    if isinstance(msg, AIMessage):
                        print(f"AI Message - Has tool_calls: {bool(getattr(msg, 'tool_calls', None))}, Content length: {len(getattr(msg, 'content', ''))}")
                        # Check if content exists and is not empty, AND tool_calls is missing or empty
                        if getattr(msg, 'content', '') and not getattr(msg, 'tool_calls', None):
                             final_response = msg.content
                             break

                if final_response:
                    st.markdown("### 🎉 Your Travel Plan:")
                    st.markdown(final_response)

                    with st.expander("🔍 Debug Info (Final State)"):
                        # --- MODIFICATION: Include all relevant state keys ---
                        st.json({
                            "thread_id": st.session_state.thread_id, # Show thread ID
                            "destination": response.get('destination', 'Not set'),
                            "budget": response.get('budget', 'Not set'),
                            "interests": response.get('interests', 'Not set'),
                            "needs_directions": response.get('needs_directions', False),
                            "feasibility": response.get('feasibility_status', 'Not set'),
                            "flight_searched": response.get('flight_searched', False),
                            "hotel_searched": response.get('hotel_searched', False),
                            "activities_searched": response.get('activities_searched', False),
                            "directions_searched": response.get('directions_searched', False), # <-- ADDED
                            "flight_carrier": response.get('flight_carrier', 'Not set'),
                            "flight_cost_eur": response.get('flight_cost_eur', 'Not set'),
                            "remaining_budget_usd": response.get('remaining_budget_usd', 'Not set')
                        })
                else:
                    st.error("Could not generate travel plan. The AI did not provide a final response.")
                    last_msg_details = "No messages found"
                    if response and response.get("messages"):
                         last_msg = response["messages"][-1]
                         last_msg_details = f"Last message type: {type(last_msg).__name__}, Content: {getattr(last_msg, 'content', 'N/A')}, Tool Calls: {getattr(last_msg, 'tool_calls', 'N/A')}"
                    st.write(last_msg_details)
                    with st.expander("🔍 Debug Info (Failure - Full State)"):
                        # Attempt to serialize the full state, handling potential errors
                        try:
                            st.json(response, default=lambda o: f"<non-serializable: {type(o).__name__}>")
                        except Exception as json_e:
                             st.write(f"Could not serialize full state: {json_e}")
                             st.write(response) # Fallback to raw output

            except Exception as e:
                st.error(f"Error: {str(e)}")
                print(f"❌ Error in graph execution: {e}")
                import traceback
                traceback.print_exc()
    else:
        st.warning("Please enter your travel request.")



