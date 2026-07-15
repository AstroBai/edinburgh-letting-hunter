"""
Umega.co.uk scraper – Edinburgh letting agency.
Search URL: https://www.umega.co.uk/properties/?location=EH9
"""
from __future__ import annotations
import re
import json
import logging

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class UmegaScraper(BaseScraper):
    SOURCE_NAME = "Umega"

    SEARCH_URL = (
        "https://www.umega.co.uk/properties/"
        "?location=EH9"
        "&department=residential-lettings"
    )

    def fetch_listings(self) -> list[dict]:
        soup = self._soup(self.SEARCH_URL)
        if soup is None:
            return []

        listings: list[dict] = []

        # JSON-LD
        ld = self._parse_ldjson(soup)
        if ld:
            return ld

        cards = (
            soup.select("div[class*=property]")
            or soup.select("div[class*=card]")
            or soup.select("article")
            or soup.select("[class*=PropertyCard]")
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
            if not link:
                return None
            href = link.get("href", "")
            url = href if href.startswith("http") else f"https://www.umega.co.uk{href}"

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
            logger.debug("[Umega] Error parsing card: %s", exc)
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
            for match in re.finditer(r'__NEXT_DATA__\s*=\s*({.*?});', text, re.DOTALL):
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, dict):
                        props = data.get("props", {}).get("pageProps", {})
                        properties = props.get("properties") or props.get("listings") or []
                        for item in properties:
                            url = item.get("url", "")
                            results.append({
                                "external_id": item.get("id", "") or url,
                                "url": url,
                                "title": item.get("title", ""),
                                "price_pcm": item.get("price") or item.get("rent"),
                                "beds": item.get("bedrooms") or item.get("beds"),
                                "address": item.get("address", ""),
                                "postcode": item.get("postcode", ""),
                            })
                except (json.JSONDecodeError, TypeError):
                    continue
        return results
