"""
Rettie.co.uk scraper – property letting in Edinburgh.
Search URL: https://www.rettie.co.uk/properties/?department=residential-lettings&location=EH9
"""
from __future__ import annotations
import re
import json
import logging

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RettieScraper(BaseScraper):
    SOURCE_NAME = "Rettie"

    SEARCH_URL = (
        "https://www.rettie.co.uk/properties/"
        "?department=residential-lettings"
        "&location=EH9"
        "&location_type=postcode"
        "&radius=1"
        "&orderby=date"
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

        # Try property cards
        cards = (
            soup.select("div[class*=property-card]")
            or soup.select("article[class*=property]")
            or soup.select("div[class*=Property]")
            or soup.select("[class*=listing]")
        )

        for card in cards:
            listing = self._parse_card(card)
            if listing:
                listings.append(listing)

        if not listings:
            listings = self._parse_embedded(soup)

        return listings

    def _parse_card(self, card) -> dict | None:
        try:
            link = card.select_one("a[href*=/property/]") or card.select_one("a[href]")
            url = ""
            if link:
                href = link.get("href", "")
                url = href if href.startswith("http") else f"https://www.rettie.co.uk{href}"

            title_el = card.select_one("h2, h3, [class*=title], [class*=address]")
            title = title_el.get_text(strip=True) if title_el else ""

            price_el = card.select_one("[class*=price]")
            price = None
            if price_el:
                pt = re.sub(r"[^\d]", "", price_el.get_text())
                if pt:
                    price = float(pt)

            beds_el = card.select_one("[class*=bed]")
            beds = None
            if beds_el:
                m = re.search(r"(\d+)", beds_el.get_text())
                if m:
                    beds = int(m.group(1))

            addr_text = card.get_text(" ", strip=True)

            return {
                "external_id": url,
                "url": url,
                "title": title,
                "price_pcm": price,
                "beds": beds,
                "address": title,
                "postcode": "",
            }
        except Exception as exc:
            logger.debug("[Rettie] Error parsing card: %s", exc)
            return None

    def _parse_ldjson(self, soup) -> list[dict]:
        results: list[dict] = []
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") in ("Product", "RealEstateListing"):
                        url = item.get("url", "")
                        results.append({
                            "external_id": url,
                            "url": url,
                            "title": item.get("name", ""),
                            "price_pcm": item.get("offers", {}).get("price") if isinstance(item.get("offers"), dict) else None,
                            "beds": None,
                            "address": item.get("address", {}).get("streetAddress", "") if isinstance(item.get("address"), dict) else "",
                        })
                    elif item.get("@type") == "ItemList" and "itemListElement" in item:
                        for el in item["itemListElement"]:
                            p = el if isinstance(el, dict) else {}
                            u = p.get("url", "")
                            if u:
                                results.append({
                                    "external_id": u,
                                    "url": u,
                                    "title": p.get("name", ""),
                                    "price_pcm": None,
                                    "beds": None,
                                    "address": "",
                                })
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        return results

    def _parse_embedded(self, soup) -> list[dict]:
        results: list[dict] = []
        for script in soup.select("script"):
            text = script.string or ""
            # Look for JSON arrays with property data
            for match in re.finditer(r'"properties"\s*:\s*(\[.*?\])\s*,', text, re.DOTALL):
                try:
                    data = json.loads(match.group(1))
                    for item in data:
                        if isinstance(item, dict):
                            url = item.get("url", "")
                            results.append({
                                "external_id": item.get("id", "") or url,
                                "url": url,
                                "title": item.get("title", ""),
                                "price_pcm": item.get("price"),
                                "beds": item.get("bedrooms"),
                                "address": item.get("address", "") or item.get("displayAddress", ""),
                            })
                except (json.JSONDecodeError, TypeError):
                    continue
        return results
