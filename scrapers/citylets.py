"""
Citylets.co.uk scraper – Edinburgh's largest letting portal.

URL patterns discovered:
  Search:   /flats-rent-{city}/  and  /houses-rent-{city}/
  Area:     /flats-rent-{city}/{neighbourhood}/
  Detail:   /property-rent/{slug}-{pid}/
  Listing:  <ul class="search-results"> → <li> → <div class="listing-content-wrapper"> → <h2>
"""
from __future__ import annotations
import re
import logging

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CityletsScraper(BaseScraper):
    SOURCE_NAME = "Citylets"

    SEARCH_URLS = [
        "https://www.citylets.co.uk/flats-rent-edinburgh/",
        "https://www.citylets.co.uk/houses-rent-edinburgh/",
        # Area-specific pages near EH9 2HZ
        "https://www.citylets.co.uk/flats-rent-edinburgh/morningside/",
        "https://www.citylets.co.uk/flats-rent-edinburgh/newington/",
        "https://www.citylets.co.uk/flats-rent-edinburgh/marchmont/",
        "https://www.citylets.co.uk/flats-rent-edinburgh/bruntsfield/",
        "https://www.citylets.co.uk/flats-rent-edinburgh/blackford/",
        "https://www.citylets.co.uk/houses-rent-edinburgh/morningside/",
        "https://www.citylets.co.uk/houses-rent-edinburgh/newington/",
    ]

    def fetch_listings(self) -> list[dict]:
        listings: list[dict] = []
        seen_urls: set[str] = set()

        for search_url in self.SEARCH_URLS:
            soup = self._soup(search_url)
            if soup is None:
                continue

            items = soup.find_all("li")
            for li in items:
                wrapper = li.find(
                    "div", class_=lambda c: c
                    and "listing-content-wrapper" in (c if isinstance(c, str) else str(c))
                )
                if not wrapper:
                    continue

                listing = self._parse_card(wrapper)
                if listing and listing["url"] not in seen_urls:
                    seen_urls.add(listing["url"])
                    listings.append(listing)

        logger.info(
            "[Citylets] %d unique listings from %d URL(s)",
            len(listings),
            len(self.SEARCH_URLS),
        )
        return listings

    def _parse_card(self, wrapper) -> dict | None:
        try:
            h2 = wrapper.find("h2")
            title = h2.get_text(strip=True) if h2 else ""

            # URL – from the first <a> in the wrapper
            link = wrapper.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else f"https://www.citylets.co.uk{href}"

            full_text = wrapper.get_text(" ", strip=True)

            # Price
            price = self._extract_price_pcm(full_text)

            # Beds
            beds = self._extract_beds(full_text)
            if beds is None:
                m = re.search(r"(\d+)\s*bed", title.lower())
                if m:
                    beds = int(m.group(1))

            # Postcode – extract outcode from URL slug (e.g. eh12-581749)
            outcode = ""
            m = re.search(r"-(eh\d{1,2})-", url.lower())
            if m:
                outcode = m.group(1).upper()

            # Also check for full postcode in text
            postcode = self._extract_postcode(full_text)
            if not postcode:
                postcode = outcode

            # Area from title (e.g. "£700 pcm 1 bed flat to rent in Barnton")
            address = title
            area_match = re.search(r"to rent in\s+(.+)$", title, re.I)
            if area_match:
                address = area_match.group(1).strip()

            return {
                "external_id": url,
                "url": url,
                "title": title,
                "price_pcm": price,
                "beds": beds,
                "address": address,
                "postcode": postcode,
            }
        except Exception as exc:
            logger.debug("[Citylets] Error parsing card: %s", exc)
            return None
