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
