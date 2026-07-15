"""
Geocoding helpers – postcode-to-coords lookup and distance calculation.

Supports both full postcodes (EH9 2HZ) and outcodes/postcode districts (EH9, EH10).
"""
from __future__ import annotations
import re
import time
import logging
from functools import lru_cache

import requests
from haversine import haversine, Unit

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-computed set of outcodes (postcode districts) within ~1 mile of EH9 2HZ
# Verified with postcodes.io areas API.
# ---------------------------------------------------------------------------
NEARBY_OUTCODES: set[str] = {
    # EH9 itself
    "EH9",
    # Adjacent districts within ~1.2 mi of EH9 2JG
    "EH8",   # Southside / Newington
    "EH10",  # Bruntsfield / Morningside
    "EH16",  # Blackford / Prestonfield
    "EH3",   # Tollcross / Fountainbridge (south end)
    "EH11",  # Gorgie / Dalry (east end)
    "EH14",  # Slateford / Longstone (east end)
    "EH1",   # Old Town (south edge)
}
# Wider set for the outcode pre-filter in base.py
BROAD_OUTCODES: set[str] = NEARBY_OUTCODES | {"EH15", "EH17", "EH22", "EH7", "EH6", "EH4", "EH12", "EH26", "EH5"}


@lru_cache(maxsize=256)
def geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Look up (lat, lng) for a UK full postcode or outcode via postcodes.io.

    - Full postcode (EH9 2HZ) → /postcodes/ endpoint
    - Outcode (EH9)         → /outcodes/ endpoint
    Returns None on failure.
    """
    code = postcode.strip().upper()

    is_full_postcode = bool(
        re.match(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2}$", code.replace(" ", ""))
    )

    if is_full_postcode:
        normalised = f"{code[:-3]} {code[-3:]}"
        endpoint = f"https://api.postcodes.io/postcodes/{normalised}"
    else:
        # Outcode – use the outcodes endpoint
        # Strip any trailing partial like "EH8" → "EH8"
        m = re.match(r"^([A-Z]{1,2}\d{1,2}[A-Z]?)", code)
        outcode = m.group(1) if m else code
        endpoint = f"https://api.postcodes.io/outcodes/{outcode}"

    try:
        resp = requests.get(
            endpoint,
            timeout=config.REQUEST_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data["status"] == 200:
                return (data["result"]["latitude"], data["result"]["longitude"])
        return None
    except requests.RequestException:
        return None


def is_within_radius(
    lat: float, lng: float,
    centre_lat: float = config.TARGET_LAT,
    centre_lng: float = config.TARGET_LON,
    radius_miles: float = config.RADIUS_MILES,
) -> bool:
    """Return True if (lat, lng) is within *radius_miles* of the centre."""
    distance = haversine(
        (centre_lat, centre_lng),
        (lat, lng),
        unit=Unit.MILES,
    )
    return distance <= radius_miles


def extract_postcode(text: str) -> str | None:
    """Pull a full UK postcode out of a free-text string.

    Returns the first matched postcode (uppercased, with space), or None.
    """
    m = re.search(
        r"(?i)\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b",
        text,
    )
    if m:
        return f"{m.group(1).upper()} {m.group(2).upper()}"
    return None


def extract_outcode(text: str) -> str | None:
    """Extract a postcode district/outcode (EH9, EH10, etc.) from text."""
    m = re.search(r"(?i)\b(EH\d{1,2})\b", text)
    if m:
        return m.group(1).upper()
    # Try URL patterns like /eh9- or eh9/
    m = re.search(r"(?i)/?(eh\d{1,2})[/-]", text)
    if m:
        return m.group(1).upper()
    return None


def estimate_location_from_text(
    text: str,
) -> tuple[float, float] | None:
    """Try to geolocate a property from its address/description text.

    First tries full postcode, then outcode.  Returns None if neither works.
    """
    pc = extract_postcode(text)
    if pc:
        coords = geocode_postcode(pc)
        if coords:
            return coords

    outcode = extract_outcode(text)
    if outcode:
        coords = geocode_postcode(outcode)
        if coords:
            return coords

    return None


def is_outcode_nearby(outcode: str) -> bool:
    """Check if an outcode is likely within ~1 mile of EH9 2HZ.

    Uses a pre-computed whitelist of adjacent postcode districts.
    """
    return outcode.upper().strip() in NEARBY_OUTCODES


def is_outcode_reasonable(outcode: str) -> bool:
    """Broader check – include slightly further districts."""
    return outcode.upper().strip() in BROAD_OUTCODES
