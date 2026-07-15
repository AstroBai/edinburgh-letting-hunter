"""
SpareRoom.co.uk scraper.

Page structure discovered:
  - Search page: <li class="listing-result" data-listing-*="...">
  - Rich data-* attributes on the <li> contain all listing info:
      data-listing-id, data-listing-postcode, data-listing-rooms-in-property,
      data-listing-title, data-listing-ad-headline-rate, data-listing-ad-headline-rate-period,
      data-listing-neighbourhood, data-listing-status, data-listing-url
"""
from __future__ import annotations
import re
import logging

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SpareRoomScraper(BaseScraper):
    SOURCE_NAME = "SpareRoom"

    SEARCH_URL = "https://www.spareroom.co.uk/flatshare/edinburgh"

    def fetch_listings(self) -> list[dict]:
        soup = self._soup(self.SEARCH_URL)
        if soup is None:
            return []

        cards = soup.select("li.listing-result")
        listings: list[dict] = []
        seen_ids: set[str] = set()

        for card in cards:
            listing = self._parse_card(card)
            if listing:
                uid = listing["external_id"]
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    listings.append(listing)

        # Also try to search with the EH9 outcode for more targeted results
        try:
            eh9_soup = self._soup("https://www.spareroom.co.uk/flatshare/?search=eh9")
            if eh9_soup:
                eh9_cards = eh9_soup.select("li.listing-result")
                for card in eh9_cards:
                    listing = self._parse_card(card)
                    if listing and listing["external_id"] not in seen_ids:
                        seen_ids.add(listing["external_id"])
                        listings.append(listing)
        except Exception:
            pass

        logger.info("[SpareRoom] %d unique listings", len(listings))
        return listings

    def _parse_card(self, card) -> dict | None:
        """Extract listing from a <li class='listing-result'> element's data attributes."""
        try:
            listing_id = card.get("data-listing-id", "")
            if not listing_id:
                return None

            title = card.get("data-listing-title", "") or ""

            # Price
            rate_str = card.get("data-listing-ad-headline-rate", "£0")
            period = card.get("data-listing-ad-headline-rate-period", "pcm")
            price = self._parse_price(rate_str, period)

            # Beds – data-listing-rooms-in-property is total rooms in the property
            rooms_str = card.get("data-listing-rooms-in-property", "")
            beds = int(rooms_str) if rooms_str and rooms_str.isdigit() else None

            # Postcode – from data attribute
            postcode = card.get("data-listing-postcode", "") or ""

            # URL
            rel_url = card.get("data-listing-url", "")
            if rel_url.startswith("/"):
                url = f"https://www.spareroom.co.uk{rel_url}"
            elif rel_url.startswith("http"):
                url = rel_url
            else:
                url = f"https://www.spareroom.co.uk/flatshare/midlothian/edinburgh/{listing_id}"

            # Neighbourhood / area
            neighbourhood = card.get("data-listing-neighbourhood", "")

            # Status
            status = card.get("data-listing-status", "")

            # Listing type (offered = room available, wanted = looking for room)
            listing_type = card.get("data-listing-type", "")

            address = neighbourhood

            return {
                "external_id": listing_id,
                "url": url,
                "title": title,
                "price_pcm": price,
                "beds": beds,
                "address": address,
                "postcode": postcode,
                "listing_type": listing_type,
            }
        except Exception as exc:
            logger.debug("[SpareRoom] Error parsing card: %s", exc)
            return None

    def _parse_price(self, rate_str: str, period: str) -> float | None:
        """Parse price string like '£250' with period 'pw' or 'pcm'."""
        m = re.search(r"£?([\d,]+)", rate_str)
        if not m:
            return None
        amount = float(m.group(1).replace(",", ""))
        period = period.lower().strip()
        if period in ("pw", "p/w", "/week", "per week"):
            return round(amount * 4.33, 2)
        if period in ("pcm", "p/m", "/month", "per month"):
            return amount
        return amount  # assume pcm
