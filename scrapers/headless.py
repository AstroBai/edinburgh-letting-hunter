"""
Headless browser scraper using Playwright.

Used for JS-rendered sites (ESPC, Rettie, Umega).
Optional – only works if Playwright is installed (pip install playwright && playwright install chromium).
"""
from __future__ import annotations
import re
import json
import logging

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE: bool | None = None


def playwright_available() -> bool:
    """Check if Playwright + Chromium are installed (lazy check)."""
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is not None:
        return _PLAYWRIGHT_AVAILABLE
    try:
        import playwright  # noqa: F401
        _PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        _PLAYWRIGHT_AVAILABLE = False
    return _PLAYWRIGHT_AVAILABLE


def fetch_page_playwright(url: str, timeout_ms: int = 30000) -> str | None:
    """Open URL in headless Chromium and return rendered HTML.

    Standalone helper (doesn't require sub-classing BaseScraper).
    Returns None if Playwright isn't installed or the page fails.
    """
    if not playwright_available():
        return None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                )
            )
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        logger.warning("Playwright fetch error for %s: %s", url, exc)
        return None


class HeadlessScraper(BaseScraper):
    """Base for scrapers that need JavaScript rendering."""

    PAGE_LOAD_TIMEOUT = 30000  # ms

    def _fetch_page(self, url: str) -> str | None:
        """Open URL in headless Chromium and return rendered HTML.

        Returns None if Playwright isn't available or page fails.
        """
        if not playwright_available():
            logger.warning("[%s] Playwright not installed – skipping JS-rendered page", self.SOURCE_NAME)
            return None

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    )
                )
                page.goto(url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            logger.warning("[%s] Playwright error: %s", self.SOURCE_NAME, exc)
            return None

    def _find_json_ld(self, html: str) -> list[dict]:
        """Extract JSON-LD scripts from rendered HTML."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") in (
                        "Product", "RealEstateListing", "ItemList"
                    ):
                        if item["@type"] == "ItemList" and "itemListElement" in item:
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
        """Convert a JSON-LD item to our standard format."""
        if not isinstance(item, dict):
            return None
        url = item.get("url", "") or item.get("@id", "") or ""
        if not url:
            return None
        address_obj = item.get("address", {}) or {}
        offers = item.get("offers", {}) or {}
        return {
            "external_id": item.get("sku", "") or url,
            "url": url,
            "title": item.get("name", ""),
            "price_pcm": offers.get("price") if isinstance(offers, dict) else None,
            "beds": None,
            "address": (
                address_obj.get("streetAddress", "")
                if isinstance(address_obj, dict)
                else ""
            ),
            "postcode": (
                address_obj.get("postalCode", "")
                if isinstance(address_obj, dict)
                else ""
            ),
        }


class EspcHeadlessScraper(HeadlessScraper):
    """ESPC – fully JS-rendered."""

    SOURCE_NAME = "ESPC"

    SEARCH_URL = "https://www.espc.com/property-to-rent/edinburgh"

    def fetch_listings(self) -> list[dict]:
        html = self._fetch_page(self.SEARCH_URL)
        if html is None:
            return []

        # Try JSON-LD
        listings = self._find_json_ld(html)
        if listings:
            return listings

        # Fallback: parse rendered HTML
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        # Note: avoid CSS selector soup.select("a[href*=/property/]")
        # because SoupSiege chokes on unescaped slashes.
        cards = (
            soup.select("article[class*=result]")
            or soup.select("[data-testid*=property]")
            or soup.select("[class*=property-card]")
            or [a for a in soup.find_all("a", href=True) if "/property/" in a["href"]]
        )

        for card in cards:
            listing = self._parse_rendered_card(card)
            if listing:
                results.append(listing)
        return results

    def _parse_rendered_card(self, card) -> dict | None:
        try:
            link = card if card.name == "a" else card.find("a", href=lambda h: h and "/property/" in h)
            if not link:
                return None
            href = link.get("href", "")
            url = href if href.startswith("http") else f"https://www.espc.com{href}"
            title = link.get_text(strip=True) or ""
            return {
                "external_id": url,
                "url": url,
                "title": title,
                "price_pcm": self._extract_price_pcm(card.get_text(" ", strip=True)),
                "beds": self._extract_beds(card.get_text(" ", strip=True)),
                "address": title,
                "postcode": self._extract_postcode(card.get_text(" ", strip=True)),
            }
        except Exception as exc:
            logger.debug("[ESPC] Error: %s", exc)
            return None


class RettieHeadlessScraper(HeadlessScraper):
    """Rettie – Cloudflare protected + JS-rendered."""

    SOURCE_NAME = "Rettie"

    SEARCH_URL = (
        "https://www.rettie.co.uk/properties/"
        "?department=residential-lettings"
        "&location=EH9"
        "&location_type=postcode"
        "&radius=1"
    )

    def fetch_listings(self) -> list[dict]:
        html = self._fetch_page(self.SEARCH_URL)
        if html is None:
            return []

        listings = self._find_json_ld(html)
        if listings:
            return listings

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        for card in soup.select("a[href*=/property/]"):
            url = card.get("href", "")
            if url.startswith("/"):
                url = f"https://www.rettie.co.uk{url}"
            title = card.get_text(strip=True)
            if title:
                results.append({
                    "external_id": url,
                    "url": url,
                    "title": title,
                    "price_pcm": self._extract_price_pcm(title),
                    "beds": self._extract_beds(title),
                    "address": title,
                    "postcode": "",
                })
        return results


class UmegaHeadlessScraper(HeadlessScraper):
    """Umega – JS-rendered."""

    SOURCE_NAME = "Umega"

    SEARCH_URL = "https://www.umega.co.uk/properties/?location=EH9&department=residential-lettings"

    def fetch_listings(self) -> list[dict]:
        html = self._fetch_page(self.SEARCH_URL)
        if html is None:
            return []

        listings = self._find_json_ld(html)
        if listings:
            return listings

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        for card in soup.select("a[href*=/property/]"):
            url = card.get("href", "")
            if url.startswith("/"):
                url = f"https://www.umega.co.uk{url}"
            title = card.get_text(strip=True)
            if title:
                results.append({
                    "external_id": url,
                    "url": url,
                    "title": title,
                    "price_pcm": self._extract_price_pcm(title),
                    "beds": self._extract_beds(title),
                    "address": title,
                    "postcode": "",
                })
        return results
