"""
Base scraper class.  All site-specific scrapers inherit from this.
"""
from __future__ import annotations
import time
import re
import logging
from abc import ABC, abstractmethod

import requests
from bs4 import BeautifulSoup

import config
from geocode import (
    estimate_location_from_text,
    is_within_radius,
    is_outcode_nearby,
)

logger = logging.getLogger(__name__)


def _get_outcode(text: str) -> str | None:
    m = re.search(r"(?i)\b(EH\d{1,2})\b", text)
    return m.group(1).upper() if m else None


def _has_full_postcode(text: str) -> bool:
    """True if at least one full postcode (XX1 1XX) appears in text."""
    return bool(
        re.search(r"(?i)\b([A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2})\b", text)
    )


class BaseScraper(ABC):
    """Subclass and implement fetch_listings() for each source."""

    SOURCE_NAME: str = "base"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape(self) -> list[dict]:
        """Run the full scrape pipeline for this source.

        Returns filtered, deduplicated listings ready for comparison.
        """
        logger.info("[%s] Starting scrape …", self.SOURCE_NAME)
        raw = self.fetch_listings()
        logger.info("[%s] Fetched %d raw listings", self.SOURCE_NAME, len(raw))

        filtered = self._filter(raw)
        logger.info(
            "[%s] %d remain after geo/bed filter",
            self.SOURCE_NAME,
            len(filtered),
        )
        return filtered

    # ------------------------------------------------------------------
    # Subclass must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_listings(self) -> list[dict]:
        """Return a list of raw listing dicts.

        Each dict MUST include at least:
            external_id  – unique within this source (URL or id)
            url          – direct link to the listing
            title        – short title
        SHOULD include:
            price_pcm    – numeric monthly rent  (or None)
            beds         – int bedroom count     (or None)
            address      – street address        (or "")
            postcode     – postcode string       (or "")
            latitude     – float                 (or None)
            longitude    – float                 (or None)
        """
        ...

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs) -> requests.Response | None:
        """GET with rate-limiting and error handling."""
        time.sleep(config.REQUEST_DELAY)
        try:
            resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning(
                "[%s] HTTP error fetching %s: %s",
                self.SOURCE_NAME, url, exc,
            )
            return None

    def _soup(self, url: str, **kwargs) -> BeautifulSoup | None:
        """Fetch URL and return BeautifulSoup object (lxml parser)."""
        resp = self._get(url, **kwargs)
        if resp is None:
            return None
        return BeautifulSoup(resp.text, "lxml")

    def _extract_postcode(self, text: str) -> str:
        """Pull a full UK postcode from any text."""
        m = re.search(
            r"(?i)\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b", text,
        )
        if m:
            return f"{m.group(1).upper()} {m.group(2).upper()}"
        return ""

    def _extract_beds(self, text: str) -> int | None:
        """Extract bedroom count from text."""
        m = re.search(r"(\d+)\s*bed", text.lower())
        if m:
            return int(m.group(1))
        return None

    def _extract_price_pcm(self, text: str) -> float | None:
        """Extract monthly rent from text (handles pcm, pw, 'per month')."""
        m = re.search(r"£\s*([\d,]+)\s*(p\.?c\.?m|per\s*month)", text.lower())
        if m:
            return float(m.group(1).replace(",", ""))
        m = re.search(r"£\s*([\d,]+)\s*(p\.?w\.?|pw|per\s*week)", text.lower())
        if m:
            return float(m.group(1).replace(",", "")) * 4.33
        m = re.search(r"£\s*([\d,]+)", text)
        if m:
            return float(m.group(1).replace(",", ""))
        return None

    def _extract_available_date(self, text: str) -> str:
        """Extract 'Available' date from text.  Returns empty string if none."""
        # "Available From: 10th July 2026" or "Available Now"
        m = re.search(
            r"(?i)(?:available|move.in)\s*(?::|from)?\s*(now|immediately|"
            r"\d{1,2}(?:st|nd|rd|th)?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})",
            text,
        )
        if m:
            raw = m.group(1)
            return f"Available {raw.capitalize()}" if raw.lower() != "now" else "Available Now"
        # "From: 30th Jun 2026" / "Available from: 30th Jun"
        m = re.search(
            r"(?i)(?:avail|from)\s*:\s*(\d{1,2}(?:st|nd|rd|th)?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})",
            text,
        )
        if m:
            return f"Available {m.group(1)}"
        return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _filter(self, listings: list[dict]) -> list[dict]:
        """Remove properties that are too far, too many beds."""
        out: list[dict] = []
        for lst in listings:
            lst["source"] = self.SOURCE_NAME

            # --- Bed filter ---
            beds = lst.get("beds")
            if beds is not None and beds > config.MAX_BEDS:
                continue

            # --- Build location text ---
            loc_text = " ".join(filter(None, [
                lst.get("address", ""),
                lst.get("postcode", ""),
                lst.get("title", ""),
                lst.get("url", ""),
            ]))
            outcode = _get_outcode(loc_text)

            # --- Decision logic ---
            lat = lst.get("latitude")
            lng = lst.get("longitude")

            if (lat is None or lng is None) and _has_full_postcode(loc_text):
                # Full postcode available – try precise geocoding
                coords = estimate_location_from_text(loc_text)
                if coords:
                    lat, lng = coords

            if lat is not None and lng is not None:
                # We have coordinates (from full postcode or native data)
                if is_within_radius(lat, lng):
                    out.append(lst)
                continue

            # No precise coordinates.
            # Trust the outcode pre-filter if available.
            if outcode and is_outcode_nearby(outcode):
                out.append(lst)

        # Extract available_date from listing text
        for lst in out:
            text = " ".join(filter(None, [
                lst.get("title", ""),
                lst.get("address", ""),
                lst.get("description", ""),
            ]))
            if not lst.get("available_date"):
                lst["available_date"] = self._extract_available_date(text)

        # Sort by price ascending
        out.sort(key=lambda x: float("inf") if x.get("price_pcm") is None else x["price_pcm"])
        return out
