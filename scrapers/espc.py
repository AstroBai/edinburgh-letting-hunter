"""
ESPC.com scraper.

Search URL for rentals in the EH9 postal area.
"""
from __future__ import annotations
import re
import json
import logging

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class EspcScraper(BaseScraper):
    SOURCE_NAME = "ESPC"

    SEARCH_URL = (
        "https://www.espc.com/property-to-rent/edinburgh/eh9"
    )

    def fetch_listings(self) -> list[dict]:
        soup = self._soup(self.SEARCH_URL)
        if soup is None:
            return []

        listings: list[dict] = []

        # Try JSON-LD first
        ld = self._parse_ldjson(soup)
        if ld:
            return ld

        # Try search results grid
        cards = (
            soup.select("article[class*=result]")
            or soup.select("div[class*=property]")
            or soup.select("li[class*=result]")
            or soup.select("[data-testid*=property]")
        )

        for card in cards:
            listing = self._parse_card(card)
            if listing:
                listings.append(listing)

        # If still empty, look for embedded JS data
        if not listings:
            listings = self._parse_embedded_js(soup)

        return listings

    def _parse_card(self, card) -> dict | None:
        try:
            # URL
            link = card.select_one("a[href]")
            url = ""
            if link:
                href = link.get("href", "")
                url = href if href.startswith("http") else f"https://www.espc.com{href}"

            title_el = card.select_one("h2, h3, [class*=title], [class*=address]")
            title = title_el.get_text(strip=True) if title_el else ""

            price_el = card.select_one("[class*=price]")
            price = None
            if price_el:
                price_text = re.sub(r"[^\d]", "", price_el.get_text())
                if price_text:
                    price = float(price_text)

            beds_el = card.select_one("[class*=bed]")
            beds = None
            if beds_el:
                m = re.search(r"(\d+)", beds_el.get_text())
                if m:
                    beds = int(m.group(1))

            addr_el = card.select_one("[class*=address], [class*=location]")
            address = addr_el.get_text(strip=True) if addr_el else title

            external_id = url

            return {
                "external_id": external_id,
                "url": url,
                "title": title,
                "price_pcm": price,
                "beds": beds,
                "address": address,
                "postcode": "",
            }
        except Exception as exc:
            logger.debug("[ESPC] Error parsing card: %s", exc)
            return None

    def _parse_ldjson(self, soup) -> list[dict]:
        results: list[dict] = []
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") in ("Product", "ItemList", "RealEstateListing"):
                        if item.get("@type") == "ItemList" and "itemListElement" in item:
                            for el in item["itemListElement"]:
                                p = self._ld_to_listing(el)
                                if p:
                                    results.append(p)
                        else:
                            p = self._ld_to_listing(item)
                            if p:
                                results.append(p)
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        return results

    def _ld_to_listing(self, item) -> dict | None:
        if isinstance(item, dict) and "url" in item.get("offers", {}):
            pass
        if not isinstance(item, dict):
            return None
        url = item.get("url", "") or ""
        return {
            "external_id": url,
            "url": url,
            "title": item.get("name", ""),
            "price_pcm": item.get("offers", {}).get("price") if isinstance(item.get("offers"), dict) else None,
            "beds": None,
            "address": item.get("address", {}).get("streetAddress", "") if isinstance(item.get("address"), dict) else "",
        } if url else None

    def _parse_embedded_js(self, soup) -> list[dict]:
        """Try to find property data in script tags with JSON."""
        results: list[dict] = []
        for script in soup.select("script"):
            text = script.string or ""
            # Look for common patterns
            for pattern in [r'results\s*=\s*(\[.*?\])\s*;', r'properties\s*:\s*(\[.*?\])']:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        for item in data:
                            results.append({
                                "external_id": item.get("id", "") or item.get("url", ""),
                                "url": item.get("url", ""),
                                "title": item.get("title") or item.get("address", ""),
                                "price_pcm": item.get("price") or item.get("rent"),
                                "beds": item.get("bedrooms") or item.get("beds"),
                                "address": item.get("address", ""),
                                "postcode": item.get("postcode", "") or item.get("postCode", ""),
                            })
                    except (json.JSONDecodeError, TypeError):
                        continue
        return results
