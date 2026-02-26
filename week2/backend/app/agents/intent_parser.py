"""Intent Parser Agent — LLM-powered parsing with minimal heuristic fast-paths."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any

from dateutil import parser as dateutil_parser
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.models.agent_state import TripState
from app.models.trip import ChatMessage, TravelStyle, TravelerType, TripRequest, TripStatus
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Style / traveler mappings (still useful for normalizing LLM output)
# ---------------------------------------------------------------------------

STYLE_MAP: dict[str, TravelStyle] = {
    "backpacking": TravelStyle.BACKPACKING,
    "budget": TravelStyle.BACKPACKING,
    "comfort": TravelStyle.COMFORT,
    "luxury": TravelStyle.LUXURY,
    "adventure": TravelStyle.ADVENTURE,
    "spiritual": TravelStyle.SPIRITUAL,
    "cultural": TravelStyle.CULTURAL,
    "family": TravelStyle.FAMILY,
    "romantic": TravelStyle.ROMANTIC,
    "honeymoon": TravelStyle.ROMANTIC,
}

TRAVELER_MAP: dict[str, TravelerType] = {
    "solo": TravelerType.SOLO,
    "couple": TravelerType.COUPLE,
    "family": TravelerType.FAMILY,
    "group": TravelerType.GROUP,
}

# Minimum viable cost lookup (INR per person per day)
MIN_COST_PER_DAY: dict[str, float] = {
    "backpacking": 1500,
    "comfort": 3000,
    "luxury": 8000,
    "adventure": 2000,
    "spiritual": 1200,
    "cultural": 2000,
    "family": 2500,
    "romantic": 4000,
}


def check_budget_feasibility(
    budget: float, days: int, styles: list[TravelStyle], traveler_count: int
) -> tuple[bool, float]:
    """Check if budget is realistic. Returns (feasible, min_estimated)."""
    if not styles:
        styles = [TravelStyle.COMFORT]
    min_per_day = min(MIN_COST_PER_DAY.get(s.value, 2000) for s in styles)
    min_total = min_per_day * days * traveler_count
    return budget >= min_total, min_total


# ---------------------------------------------------------------------------
# LLM-powered extraction
# ---------------------------------------------------------------------------

async def _llm_extract_all(text: str) -> dict[str, Any]:
    """Use LLM to extract ALL structured travel fields from any natural-language input.

    Handles any budget format (₹15000, 2 lakh, 15k, 200000 rupees, $500, etc.)
    as well as dates, duration, destination, origin, styles, and traveler info.
    """
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_REASONING,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
    )

    today = date.today().isoformat()

    prompt = f"""You are a travel-intent extraction engine. Extract structured fields from the user's text.

Today's date: {today}

User text: \"\"\"{text}\"\"\"

Return a JSON object. Only include fields you can confidently extract. Use null for unknown fields.

{{
  "destination": "city or region name",
  "origin": "departure city or region",
  "budget": 15000,           // ALWAYS a plain number in the detected currency. Convert '2 lakh' to 200000, '15k' to 15000, etc.
  "currency": "INR",         // ISO code: INR, USD, EUR, GBP, etc. Default INR for rupees/rs/₹
  "duration_days": 4,        // integer number of days
  "start_date": "YYYY-MM-DD",// resolved date (e.g., 'next weekend' → actual Saturday date, 'March 15' → '{date.today().year}-03-15')
  "end_date": "YYYY-MM-DD",
  "traveler_type": "solo",   // one of: solo, couple, family, group
  "traveler_count": 1,       // number of travelers
  "children_count": 0,
  "styles": ["adventure"],   // list from: backpacking, comfort, luxury, adventure, spiritual, cultural, family, romantic
  "interests": ["rafting"]   // specific activities/themes the user mentioned
}}

Rules:
- budget MUST be a plain number, not a string. '2 lakh rupees' = 200000, '15k' = 15000, '₹1,00,000' = 100000.
- If the user just typed a number (like "200000" or "2000 rs"), that IS the budget.
- For 'next weekend', calculate the actual upcoming Saturday from today ({today}).
- Return ONLY valid JSON, no markdown fences, no explanation."""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # Strip optional markdown code fences
        content = re.sub(r"^```[a-z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        parsed = json.loads(content.strip())
        logger.info("LLM extracted intent: %s", parsed)
        return parsed
    except Exception as e:
        logger.error("LLM intent extraction failed: %s", e)
        return {}


def _normalize_styles(raw_styles: list[str] | None) -> list[TravelStyle]:
    """Convert LLM-returned style strings to TravelStyle enums."""
    if not raw_styles:
        return []
    result: list[TravelStyle] = []
    for s in raw_styles:
        mapped = STYLE_MAP.get(s.lower().strip())
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def _normalize_traveler_type(raw: str | None) -> TravelerType:
    """Convert LLM-returned traveler type string to enum."""
    if not raw:
        return TravelerType.SOLO
    return TRAVELER_MAP.get(raw.lower().strip(), TravelerType.SOLO)


def _parse_date_safe(val: str | None) -> date | None:
    """Safely parse a date string."""
    if not val:
        return None
    try:
        return dateutil_parser.parse(val).date()
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def parse_intent(state: TripState) -> TripState:
    """Parse user intent from chat messages — LLM-first approach."""
    trip_id = state.get("trip_id", "")
    messages = state.get("chat_history", [])
    current_msg = state.get("current_message", "")

    await sse_manager.emit_phase_update(trip_id, "understand", "parsing", "Analyzing your preferences...")

    # Combine all user messages into a single block for the LLM
    all_text = " ".join(
        m.content if isinstance(m, ChatMessage) else m.get("content", "")
        for m in messages
        if (m.role if isinstance(m, ChatMessage) else m.get("role", "")) == "user"
    )
    if current_msg:
        all_text += " " + current_msg

    # Get existing request (may already have some fields from prior rounds)
    request = state.get("request") or TripRequest()
    if isinstance(request, dict):
        request = TripRequest(**request)

    request.raw_input = all_text

    # ---- LLM extraction (the single source of truth) ----
    await sse_manager.emit_agent_thinking(
        trip_id, "intent_parser",
        "Using AI to understand your travel preferences..."
    )
    try:
        extracted = await _llm_extract_all(all_text)
    except Exception as e:
        logger.error("LLM extraction failed: %s", e)
        extracted = {}

    # Merge LLM results into request — only fill fields that are still empty
    if not request.destination and extracted.get("destination"):
        request.destination = extracted["destination"]
    if not request.origin and extracted.get("origin"):
        request.origin = extracted["origin"]

    # Budget — always trust LLM if current budget is 0
    if not request.budget and extracted.get("budget"):
        try:
            request.budget = float(extracted["budget"])
        except (TypeError, ValueError):
            pass
    if extracted.get("currency"):
        request.currency = str(extracted["currency"]).upper()

    # Duration
    if not request.duration_days and extracted.get("duration_days"):
        try:
            request.duration_days = int(extracted["duration_days"])
        except (TypeError, ValueError):
            pass

    # Dates
    if request.start_date is None and extracted.get("start_date"):
        request.start_date = _parse_date_safe(extracted["start_date"])
    if request.end_date is None and extracted.get("end_date"):
        request.end_date = _parse_date_safe(extracted["end_date"])
    # Infer end_date from start + duration
    if request.start_date and not request.end_date and request.duration_days:
        request.end_date = request.start_date + timedelta(days=request.duration_days - 1)

    # Traveler
    if extracted.get("traveler_type"):
        request.traveler_type = _normalize_traveler_type(extracted["traveler_type"])
    if extracted.get("traveler_count"):
        try:
            request.traveler_count = int(extracted["traveler_count"])
        except (TypeError, ValueError):
            pass
    if extracted.get("children_count"):
        try:
            request.children_count = int(extracted["children_count"])
        except (TypeError, ValueError):
            pass

    # Styles
    if not request.styles and extracted.get("styles"):
        request.styles = _normalize_styles(extracted["styles"])

    # Interests
    if extracted.get("interests"):
        request.interests = extracted["interests"]

    # ---- Determine missing fields & respond ----
    missing = _get_missing_fields(request)

    state["request"] = request
    state["status"] = TripStatus.GATHERING_INTENT if missing else TripStatus.CHECKPOINT_1

    if missing:
        follow_up = _generate_follow_up(missing)
        history = list(state.get("chat_history", []))
        history.append({"role": "assistant", "content": follow_up})
        state["chat_history"] = history
    else:
        # Check budget feasibility
        feasible, min_est = check_budget_feasibility(
            request.budget, request.duration_days, request.styles, request.traveler_count
        )
        state["budget_feasible"] = feasible
        if not feasible:
            state["budget_warnings"] = [
                f"Your budget of {request.currency} {request.budget:,.0f} may be tight "
                f"for a {request.duration_days}-day trip. "
                f"Minimum estimated: {request.currency} {min_est:,.0f}."
            ]

    return state


# ---------------------------------------------------------------------------
# Missing-field helpers (unchanged)
# ---------------------------------------------------------------------------

def _get_missing_fields(request: TripRequest) -> list[str]:
    """Return list of missing required fields."""
    missing = []
    if not request.destination:
        missing.append("destination")
    if not request.origin:
        missing.append("origin")
    if request.duration_days <= 0:
        missing.append("duration")
    if request.budget <= 0:
        missing.append("budget")
    return missing


def _generate_follow_up(missing: list[str]) -> str:
    """Generate a follow-up question for missing fields."""
    questions = {
        "destination": "Where would you like to go? 🌍",
        "origin": "Where will you be traveling from?",
        "duration": "How many days are you planning for?",
        "budget": "What's your approximate budget for this trip?",
    }
    parts = [questions[f] for f in missing if f in questions]
    return " ".join(parts)
