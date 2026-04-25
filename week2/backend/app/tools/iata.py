"""IATA airport code lookup for Indian and popular international cities."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# City name (lowercase) → IATA code
# When a city has no direct airport, mapped to the nearest airport
CITY_TO_IATA: dict[str, str] = {
    # --- Major Indian cities ---
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "mumbai": "BOM",
    "bombay": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "hyderabad": "HYD",
    "chennai": "MAA",
    "madras": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "pune": "PNQ",
    "ahmedabad": "AMD",
    "goa": "GOI",
    "panaji": "GOI",
    "jaipur": "JAI",
    "kochi": "COK",
    "cochin": "COK",
    "lucknow": "LKO",
    "chandigarh": "IXC",
    "amritsar": "ATQ",
    "varanasi": "VNS",
    "banaras": "VNS",
    "bhopal": "BHO",
    "indore": "IDR",
    "nagpur": "NAG",
    "patna": "PAT",
    "ranchi": "IXR",
    "bhubaneswar": "BBI",
    "visakhapatnam": "VTZ",
    "vizag": "VTZ",
    "coimbatore": "CJB",
    "madurai": "IXM",
    "trichy": "TRZ",
    "tiruchirappalli": "TRZ",
    "mangalore": "IXE",
    "mangaluru": "IXE",
    "srinagar": "SXR",
    "leh": "IXL",
    "ladakh": "IXL",
    "jammu": "IXJ",
    "dehradun": "DED",
    "jodhpur": "JDH",
    "udaipur": "UDR",
    "aurangabad": "IXU",
    "guwahati": "GAU",
    "bagdogra": "IXB",
    "siliguri": "IXB",
    "port blair": "IXZ",
    "andaman": "IXZ",
    "agra": "AGR",
    "kullu": "KUU",
    "manali": "KUU",
    "kullu manali": "KUU",
    "shimla": "SLV",
    "hubli": "HBX",
    "belgaum": "IXG",
    "belagavi": "IXG",
    "mysore": "MYQ",
    "mysuru": "MYQ",
    "tirupati": "TIR",
    "raipur": "RPR",
    "bhopal": "BHO",
    "jabalpur": "JLR",
    "surat": "STV",
    "vadodara": "BDQ",
    "rajkot": "RAJ",
    "bhuj": "BHJ",
    "dibrugarh": "DIB",
    "imphal": "IMF",
    "aizawl": "AJL",
    "agartala": "IXA",
    "shillong": "SHL",
    "kohima": "DMU",
    "dimapur": "DMU",

    # Rishikesh → nearest airport is Jolly Grant, Dehradun
    "rishikesh": "DED",
    # Haridwar → Jolly Grant, Dehradun
    "haridwar": "DED",
    # Nainital → Pantnagar
    "nainital": "PGH",
    # Mussoorie → Dehradun
    "mussoorie": "DED",
    # Dharamsala / McLeod Ganj → Gaggal
    "dharamsala": "DHM",
    "mcleod ganj": "DHM",
    "mcleodganj": "DHM",
    # Spiti → Shimla or Kullu
    "spiti": "KUU",
    # Munnar/Kerala hill stations → Cochin
    "munnar": "COK",
    "thekkady": "COK",
    "alleppey": "COK",
    "alappuzha": "COK",
    # Hampi → Hubli
    "hampi": "HBX",
    # Khajuraho
    "khajuraho": "HJR",
    # Jaisalmer
    "jaisalmer": "JSA",
    # Bikaner
    "bikaner": "BKB",
    # Ranthambore → Jaipur or Kota
    "ranthambore": "JAI",
    "sawai madhopur": "JAI",
    # Ooty → Coimbatore
    "ooty": "CJB",
    "udhagamandalam": "CJB",
    # Kodaikanal → Madurai
    "kodaikanal": "IXM",
    # Pondicherry → Chennai
    "pondicherry": "MAA",
    "puducherry": "MAA",
    # Mahabaleshwar → Pune
    "mahabaleshwar": "PNQ",
    "lonavala": "PNQ",
    # Darjeeling → Bagdogra
    "darjeeling": "IXB",
    "gangtok": "IXB",
    "sikkim": "IXB",

    # --- Popular international destinations ---
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "singapore": "SIN",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "kl": "KUL",
    "london": "LHR",
    "paris": "CDG",
    "new york": "JFK",
    "nyc": "JFK",
    "los angeles": "LAX",
    "la": "LAX",
    "tokyo": "NRT",
    "sydney": "SYD",
    "melbourne": "MEL",
    "toronto": "YYZ",
    "hong kong": "HKG",
    "amsterdam": "AMS",
    "frankfurt": "FRA",
    "zurich": "ZRH",
    "istanbul": "IST",
    "doha": "DOH",
    "muscat": "MCT",
    "kathmandu": "KTM",
    "colombo": "CMB",
    "dhaka": "DAC",
    "karachi": "KHI",
    "lahore": "LHE",
    "nairobi": "NBO",
    "johannesburg": "JNB",
    "cape town": "CPT",
    "bali": "DPS",
    "denpasar": "DPS",
    "jakarta": "CGK",
    "ho chi minh": "SGN",
    "saigon": "SGN",
    "hanoi": "HAN",
    "phuket": "HKT",
    "chiang mai": "CNX",
    "seoul": "ICN",
    "beijing": "PEK",
    "shanghai": "PVG",
    "guangzhou": "CAN",
    "taipei": "TPE",
    "manila": "MNL",
    "jakarta": "CGK",
    "rome": "FCO",
    "milan": "MXP",
    "barcelona": "BCN",
    "madrid": "MAD",
    "lisbon": "LIS",
    "vienna": "VIE",
    "prague": "PRG",
    "warsaw": "WAW",
    "budapest": "BUD",
    "athens": "ATH",
    "cairo": "CAI",
    "casablanca": "CMN",
    "mexico city": "MEX",
    "sao paulo": "GRU",
    "buenos aires": "EZE",
    "lima": "LIM",
    "bogota": "BOG",
    "miami": "MIA",
    "chicago": "ORD",
    "san francisco": "SFO",
    "seattle": "SEA",
    "washington": "IAD",
    "dc": "IAD",
    "dallas": "DFW",
    "houston": "IAH",
}


def city_to_iata(city: str) -> str | None:
    """Convert a city name to an IATA airport code.

    Returns the IATA code if found, otherwise None.
    """
    return CITY_TO_IATA.get(city.lower().strip())


# Build reverse mapping: IATA code → canonical city name (first match wins)
_IATA_TO_CITY: dict[str, str] = {}
_seen_codes: set[str] = set()
for _city, _code in CITY_TO_IATA.items():
    if _code not in _seen_codes:
        _IATA_TO_CITY[_code] = _city.title()
        _seen_codes.add(_code)


def iata_to_city(code: str) -> str | None:
    """Convert an IATA airport code to its city name. Returns None if unknown."""
    return _IATA_TO_CITY.get(code.upper().strip())


def airport_city_for(destination: str) -> str | None:
    """Return the airport city if the destination's nearest airport is in a different city.

    Returns the airport city name (e.g. "Kochi" for destination "Munnar"),
    or None if the destination has its own airport (e.g. "Delhi" → None).
    """
    dest_lower = destination.lower().strip()
    iata = CITY_TO_IATA.get(dest_lower)
    if not iata:
        return None
    airport_city = _IATA_TO_CITY.get(iata)
    if not airport_city:
        return None
    if airport_city.lower() == dest_lower:
        return None
    # Check if destination is a known alias (same physical city, different name)
    if dest_lower in _AIRPORT_ALIASES.get(iata, set()):
        return None
    return airport_city


# Aliases: city names that are alternate names for the SAME physical airport city.
# Entries NOT listed here that share an IATA code are assumed to be different
# cities that use a nearby airport (e.g. Munnar → COK is NOT an alias of Kochi).
_AIRPORT_ALIASES: dict[str, set[str]] = {
    "BOM": {"mumbai", "bombay"},
    "DEL": {"delhi", "new delhi"},
    "MAA": {"chennai", "madras"},
    "CCU": {"kolkata", "calcutta"},
    "COK": {"kochi", "cochin"},
    "VTZ": {"visakhapatnam", "vizag"},
    "BLR": {"bangalore", "bengaluru"},
    "IXE": {"mangalore", "mangaluru"},
    "IXG": {"belgaum", "belagavi"},
    "MYQ": {"mysore", "mysuru"},
    "TRZ": {"trichy", "tiruchirappalli"},
    "VNS": {"varanasi", "banaras"},
    "IXB": {"bagdogra", "siliguri"},
    "IXZ": {"port blair", "andaman"},
    "KUU": {"kullu", "kullu manali"},
    "DMU": {"kohima", "dimapur"},
    "DPS": {"bali", "denpasar"},
    "SGN": {"ho chi minh", "saigon"},
    "JFK": {"new york", "nyc"},
    "LAX": {"los angeles", "la"},
    "KUL": {"kuala lumpur", "kl"},
    "IAD": {"washington", "dc"},
}


def resolve_iata(city: str) -> str:
    """Return IATA code for a city, or the original string if not found.

    Logs a warning when no mapping exists so it's visible in logs.
    """
    code = city_to_iata(city)
    if code:
        logger.debug("Resolved '%s' → %s", city, code)
        return code
    # Already looks like an IATA code (3 uppercase letters)?
    stripped = city.strip()
    if len(stripped) == 3 and stripped.isupper():
        return stripped
    logger.warning("No IATA code found for '%s'; using as-is (may fail API call)", city)
    return stripped
