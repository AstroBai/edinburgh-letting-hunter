"""
Multi-site scraper for smaller Edinburgh letting agents.
Each source has a config entry with URL + extraction strategy.
"""
from __future__ import annotations
import re
import json
import logging
from typing import Any

from bs4 import BeautifulSoup

import config
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class OtherAgentsScraper(BaseScraper):
    """Generic scraper that handles multiple small agency sites.

    Subclass for each agency by setting SOURCE_NAME + SEARCH_URL +
    overriding _parse_card() or _extract_strategy().
    """

    SOURCE_NAME = "Other"
    SEARCH_URL = ""
    # How to extract listings:
    #   "html" — parse HTML property cards
    #   "json_ld" — extract from JSON-LD
    #   "embedded_js" — look for window.__DATA__ patterns
    EXTRACT_STRATEGY = "html"

    # CSS selectors for listing cards (tried in order)
    CARD_SELECTORS = [
        "article[class*=property]",
        "div[class*=property-card]",
        "div[class*=PropertyCard]",
        "div[class*=listing]",
        "li[class*=property]",
        "div[class*=result]",
        "div[class*=card]",
        "div[class*=item]",
        "article",
    ]

    def fetch_listings(self) -> list[dict]:
        if not self.SEARCH_URL:
            return []

        soup = self._soup(self.SEARCH_URL)
        if soup is None:
            return []

        if self.EXTRACT_STRATEGY == "json_ld":
            return self._extract_json_ld(soup)
        elif self.EXTRACT_STRATEGY == "embedded_js":
            return self._extract_embedded_js(soup)
        else:
            return self._extract_html(soup)

    # ------------------------------------------------------------------
    # HTML extraction
    # ------------------------------------------------------------------

    def _extract_html(self, soup) -> list[dict]:
        for selector in self.CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                listings = []
                for card in cards:
                    lst = self._parse_card(card)
                    if lst:
                        listings.append(lst)
                if listings:
                    return listings
        return []

    def _parse_card(self, card) -> dict | None:
        """Override in subclass for site-specific parsing."""
        return None

    # ------------------------------------------------------------------
    # JSON-LD extraction
    # ------------------------------------------------------------------

    def _extract_json_ld(self, soup) -> list[dict]:
        results: list[dict] = []
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    listing = self._ld_to_listing(item)
                    if listing:
                        results.append(listing)
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        return results

    def _ld_to_listing(self, item: dict) -> dict | None:
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
            "address": address_obj.get("streetAddress", "") if isinstance(address_obj, dict) else "",
            "postcode": address_obj.get("postalCode", "") if isinstance(address_obj, dict) else "",
        }

    # ------------------------------------------------------------------
    # Embedded JS extraction
    # ------------------------------------------------------------------

    def _extract_embedded_js(self, soup) -> list[dict]:
        """Search script tags for JSON with property data."""
        results: list[dict] = []
        for script in soup.find_all("script"):
            text = script.string or ""
            if len(text) < 200:
                continue
            for pattern in [
                r'"results"\s*:\s*(\[.*?\])\s*[,;]',
                r'"properties"\s*:\s*(\[.*?\])\s*[,;]',
                r'"listings"\s*:\s*(\[.*?\])\s*[,;]',
                r'__NEXT_DATA__\s*=\s*({.*?});',
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'__NUXT__\s*=\s*({.*?});',
            ]:
                for match in re.finditer(pattern, text, re.DOTALL):
                    try:
                        data = json.loads(match.group(1))
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            listing = self._js_to_listing(item)
                            if listing:
                                results.append(listing)
                    except (json.JSONDecodeError, TypeError):
                        continue
        return results

    def _js_to_listing(self, item: dict) -> dict | None:
        """Convert a JS-embedded item to our listing format."""
        url = item.get("url", "") or item.get("slug", "") or item.get("id", "") or ""
        if not url:
            return None
        title = item.get("title", "") or item.get("name", "") or ""
        price = item.get("price", item.get("rent", item.get("pricePcm", None)))
        beds = item.get("bedrooms", item.get("beds", item.get("bedroomCount", None)))
        address = item.get("address", "") or item.get("displayAddress", "") or item.get("location", "") or ""
        postcode = item.get("postcode", "") or item.get("postCode", "") or item.get("postalCode", "") or ""
        return {
            "external_id": item.get("id", "") or url,
            "url": url if url.startswith("http") else "",
            "title": title,
            "price_pcm": float(price) if price else None,
            "beds": int(beds) if beds else None,
            "address": address,
            "postcode": postcode,
        }


# ======================================================================
# Concrete scraper classes for each agency
# ======================================================================


class S1HomesScraper(OtherAgentsScraper):
    """s1homes.com — large Scottish property portal."""
    SOURCE_NAME = "s1homes"
    SEARCH_URL = "https://www.s1homes.com/property-to-rent/Edinburgh/"
    CARD_SELECTORS = ["div[class*=result]", "div[class*=property]", "div[class*=PropertyCard]", "li[class*=result]"]
    EXTRACT_STRATEGY = "html"

    def _parse_card(self, card) -> dict | None:
        try:
            text = card.get_text(" ", strip=True)
            link = card.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else f"https://www.s1homes.com{href}"
            title = link.get_text(strip=True) if link else ""
            if not title:
                title = (card.find(["h2", "h3", "h4"]) or card).get_text(strip=True)[:80]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            return {
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            }
        except Exception as exc:
            logger.debug("[s1homes] Parse error: %s", exc)
            return None


class BelvoirScraper(OtherAgentsScraper):
    """Belvoir — national letting agency, Edinburgh branch."""
    SOURCE_NAME = "Belvoir"
    SEARCH_URL = "https://www.belvoir.co.uk/estate-agents-and-letting-agents/branch/edinburgh/property-to-rent/"
    CARD_SELECTORS = ["div[class*=property]", "div[class*=PropertyCard]", "div[class*=card]", "article", "li[class*=result]"]
    EXTRACT_STRATEGY = "html"

    def _parse_card(self, card) -> dict | None:
        try:
            text = card.get_text(" ", strip=True)
            # Use the second link (address) rather than the first ("To Let")
            links = card.find_all("a", href=True)
            link = links[1] if len(links) > 1 else (links[0] if links else None)
            if not link:
                return None
            href = link["href"]
            url = href if href.startswith("http") else f"https://www.belvoir.co.uk{href}"
            title = link.get_text(strip=True) or text[:80]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            return {
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            }
        except Exception as exc:
            logger.debug("[Belvoir] Parse error: %s", exc)
            return None


class NorthwoodScraper(OtherAgentsScraper):
    """Northwood — national letting agency, Edinburgh branch."""
    SOURCE_NAME = "Northwood"
    SEARCH_URL = "https://www.northwooduk.com/estate-agents-and-letting-agents/branch/edinburgh/property-to-rent/"
    CARD_SELECTORS = ["div[class*=property]", "div[class*=card]", "div[class*=PropertyCard]", "article", "li[class*=result]"]
    EXTRACT_STRATEGY = "html"

    def _parse_card(self, card) -> dict | None:
        try:
            text = card.get_text(" ", strip=True)
            links = card.find_all("a", href=True)
            link = links[1] if len(links) > 1 else (links[0] if links else None)
            if not link:
                return None
            href = link["href"]
            url = href if href.startswith("http") else f"https://www.northwooduk.com{href}"
            title = link.get_text(strip=True) or text[:80]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            return {
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            }
        except Exception as exc:
            logger.debug("[Northwood] Parse error: %s", exc)
            return None


class AFlatInTownScraper(OtherAgentsScraper):
    """A Flat in Town — Edinburgh letting agent."""
    SOURCE_NAME = "A Flat in Town"
    SEARCH_URL = "https://www.aflatintown.com/prop-list-half-map/"
    EXTRACT_STRATEGY = "embedded_js"

    def _js_to_listing(self, item: dict) -> dict | None:
        url = item.get("url", "") or item.get("slug", "") or item.get("id", "") or ""
        if url and not url.startswith("http"):
            url = f"https://www.aflatintown.com{url}" if url.startswith("/") else url
        if not url:
            return None
        return {
            "external_id": item.get("id", "") or url,
            "url": url,
            "title": item.get("title", "") or item.get("address", "") or item.get("name", ""),
            "price_pcm": item.get("price", item.get("rent", item.get("price_pcm", None))),
            "beds": item.get("beds", item.get("bedrooms", item.get("bedroom_count", None))),
            "address": item.get("address", "") or item.get("display_address", "") or "",
            "postcode": item.get("postcode", "") or item.get("post_code", "") or "",
        }


class S1HomesScraper(OtherAgentsScraper):
    """s1homes.com — React-rendered portal, needs Playwright."""
    SOURCE_NAME = "s1homes"
    SEARCH_URL = "https://www.s1homes.com/property-to-rent/Edinburgh/"
    EXTRACT_STRATEGY = "html"

    def fetch_listings(self) -> list[dict]:
        """s1homes is JS-rendered (React/Ant). Try headless, else skip."""
        from scrapers.headless import playwright_available, fetch_page_playwright
        if playwright_available():
            try:
                html = fetch_page_playwright(self.SEARCH_URL)
                if html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "lxml")
                    results = []
                    for a in soup.find_all("a", href=True):
                        text = a.get_text(strip=True)
                        if not text or len(text) < 10:
                            continue
                        if any(x in text.lower() for x in ["£", "bed", "flat", "apartment"]):
                            href = a["href"]
                            url = href if href.startswith("http") else f"https://www.s1homes.com{href}"
                            results.append({
                                "external_id": url,
                                "url": url, "title": text,
                                "price_pcm": self._extract_price_pcm(text),
                                "beds": self._extract_beds(text),
                                "address": text, "postcode": "",
                            })
                    return results
            except Exception as exc:
                logger.warning("[s1homes] Headless parse error: %s", exc)
        logger.info("[s1homes] Skipped (JS-rendered, no Playwright data)")
        return []


class DoveDaviesScraper(OtherAgentsScraper):
    """Dove Davies — Edinburgh letting agent."""
    SOURCE_NAME = "Dove Davies"
    SEARCH_URL = "https://www.dovedavies.com/property-to-let/"
    EXTRACT_STRATEGY = "html"

    def _extract_html(self, soup) -> list[dict]:
        """Cards are in div.col-md-7 with a link and price in p.property-price."""
        listings = []
        for div in soup.select("div.col-md-7"):
            link = div.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else f"https://www.dovedavies.com{href}"
            text = div.get_text(" ", strip=True)
            if not any(x in text.lower() for x in ["£", "flat", "apartment", "house", "studio"]):
                continue
            # Title = first part of text before price
            title = text[:100]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            listings.append({
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            })
        return listings


class GlenhamScraper(OtherAgentsScraper):
    """Glenham Property — Edinburgh lettings."""
    SOURCE_NAME = "Glenham"
    SEARCH_URL = "https://www.glenhamproperty.co.uk/properties-for-rent/"
    EXTRACT_STRATEGY = "html"

    def _extract_html(self, soup) -> list[dict]:
        listings = []
        for card in soup.select(".singleProperty"):
            text = card.get_text(" ", strip=True)
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else f"https://www.glenhamproperty.co.uk{href}"
            title = link.get_text(strip=True) or text[:80]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            listings.append({
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            })
        return listings


class FactotumScraper(OtherAgentsScraper):
    """Factotum → now Murray & Currie."""
    SOURCE_NAME = "Murray & Currie"
    SEARCH_URL = "https://murrayandcurrie.com/properties-to-rent/"
    EXTRACT_STRATEGY = "html"

    def _extract_html(self, soup) -> list[dict]:
        """Cards are Elementor loop items (.e-loop-item)."""
        listings = []
        for item in soup.select(".e-loop-item"):
            link = item.find("a", href=lambda h: h and "/property/" in h)
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else f"https://murrayandcurrie.com{href}"
            text = item.get_text(" ", strip=True)
            if "to let" not in text.lower() and "£" not in text:
                continue
            title = text[:100]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            listings.append({
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            })
        return listings


class CornerstoneScraper(OtherAgentsScraper):
    """Cornerstone Letting — Edinburgh lettings."""
    SOURCE_NAME = "Cornerstone"
    SEARCH_URL = "https://www.cornerstoneletting.com/properties/long-term-lets/"
    EXTRACT_STRATEGY = "html"
    CARD_SELECTORS = ["div[class*=property]", "div[class*=PropertyBox]", "div[class*=card]", "div[class*=item]", "article"]

    def _parse_card(self, card) -> dict | None:
        try:
            text = card.get_text(" ", strip=True)
            link = card.find("a", href=True)
            if not link:
                return None
            href = link["href"]
            url = href if href.startswith("http") else f"https://www.cornerstoneletting.com{href}"
            title = (card.find(["h2", "h3", "h4"]) or card).get_text(strip=True)[:100]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            return {
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            }
        except Exception as exc:
            logger.debug("[Cornerstone] Parse error: %s", exc)
            return None


class SouthsideMgmtScraper(OtherAgentsScraper):
    """Southside Management — renders listings via JS/Elementor.
    Uses Playwright to get the rendered HTML, then parses text.
    """
    SOURCE_NAME = "Southside Mgmt"
    SEARCH_URL = "https://southsidemanagement.com/rentals/"
    EXTRACT_STRATEGY = "html"

    def fetch_listings(self) -> list[dict]:
        from scrapers.headless import playwright_available, fetch_page_playwright
        if not playwright_available():
            logger.info("[Southside Mgmt] Playwright not installed")
            return []
        try:
            html = fetch_page_playwright(self.SEARCH_URL, timeout_ms=45000)
            if not html:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            return self._extract_text_listings(soup)
        except Exception as exc:
            logger.warning("[Southside Mgmt] Error: %s", exc)
            return []

    def _extract_text_listings(self, soup) -> list[dict]:
        """Parse listings from the rendered text format:
        £X pcm Ref Address, POSTCODE PropertyType Beds Baths Available...
        """
        import re
        results = []
        body = soup.get_text(" ", strip=True)

        # Each listing is preceded by "View property details"
        for chunk in body.split("View property details"):
            if "£" not in chunk:
                continue
            text = chunk.strip()
            price_m = re.search(r"£\s*([\d,]+)\s*p\.?c\.?m", text.lower())
            if not price_m:
                continue
            price = float(price_m.group(1).replace(",", ""))
            postcode = self._extract_postcode(text)
            beds = self._extract_beds(text)
            if beds is None:
                # Try "Flat 2 1" style — beds before bathrooms
                parts = re.findall(r"(Terraced House|Flat|House|Studio)\s+(\d+)\s+\d+", text, re.I)
                if parts:
                    beds = int(parts[0][1])
            title = text[:100] or ""
            external_id = postcode or title[:30]
            url = self.SEARCH_URL
            results.append({
                "external_id": external_id,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            })
        return results


class EdinburghLettingCentreScraper(OtherAgentsScraper):
    """Edinburgh Letting Centre."""
    SOURCE_NAME = "Edinburgh LC"
    SEARCH_URL = "https://properties.edinburghlettingcentre.com/"
    EXTRACT_STRATEGY = "html"
    CARD_SELECTORS = ["div[class*=property]", "div[class*=card]", "div[class*=PropertyCard]", "div[class*=listing]", "article"]

    def _parse_card(self, card) -> dict | None:
        try:
            text = card.get_text(" ", strip=True)
            link = card.find("a", href=True)
            if not link:
                return None
            href = link["href"]
            url = href if href.startswith("http") else f"https://properties.edinburghlettingcentre.com{href}"
            title = link.get_text(strip=True) or (card.find(["h2", "h3", "h4"]) or card).get_text(strip=True)[:80]
            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            return {
                "external_id": url,
                "url": url, "title": title,
                "price_pcm": price, "beds": beds,
                "address": title, "postcode": postcode,
            }
        except Exception as exc:
            logger.debug("[EdinburghLC] Parse error: %s", exc)
            return None


class DJAlexanderScraper(OtherAgentsScraper):
    """DJ Alexander — JS-rendered site, needs Playwright."""
    SOURCE_NAME = "DJ Alexander"
    SEARCH_URL = "https://www.djalexander.co.uk/property/to-rent/in-edinburgh/"
    EXTRACT_STRATEGY = "html"

    def fetch_listings(self) -> list[dict]:
        """DJ Alexander is JS-rendered. Try headless if available."""
        from scrapers.headless import playwright_available, fetch_page_playwright
        if playwright_available():
            try:
                html = fetch_page_playwright(self.SEARCH_URL)
                if html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "lxml")
                    results = []
                    for a in soup.find_all("a", href=lambda h: h and "/property/to-rent/" in h):
                        text = a.get_text(strip=True)
                        href = a["href"]
                        url = href if href.startswith("http") else f"https://www.djalexander.co.uk{href}"
                        results.append({
                            "external_id": url,
                            "url": url, "title": text or url,
                            "price_pcm": self._extract_price_pcm(text),
                            "beds": self._extract_beds(text),
                            "address": text, "postcode": "",
                        })
                    return results
            except Exception as exc:
                logger.warning("[DJ Alexander] Headless error: %s", exc)
        logger.info("[DJ Alexander] Skipped (JS-rendered)")
        return []


class ClanGordonScraper(OtherAgentsScraper):
    """Clan Gordon — Edinburgh letting agent.  Uses Playwright."""
    SOURCE_NAME = "Clan Gordon"
    SEARCH_URL = "https://www.clangordon.co.uk/edinburgh-property-search/"
    EXTRACT_STRATEGY = "html"

    def fetch_listings(self) -> list[dict]:
        from scrapers.headless import playwright_available, fetch_page_playwright
        if not playwright_available():
            logger.info("[Clan Gordon] Playwright not installed")
            return []
        try:
            html = fetch_page_playwright(self.SEARCH_URL, timeout_ms=30000)
            if not html:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            return self._parse_listings(soup)
        except Exception as exc:
            logger.warning("[Clan Gordon] Error: %s", exc)
            return []

    def _parse_listings(self, soup) -> list[dict]:
        import re
        results = []
        seen_urls = set()

        # Extract from property-page links using parent card text
        for link in soup.find_all("a", href=re.compile(r"/property/")):
            href = link["href"]
            url = href if href.startswith("http") else f"https://www.clangordon.co.uk{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Walk up from the link to find the <li> card with type-property
            card = link
            for _ in range(5):
                card = card.parent if card else None
                if card and card.name == "li":
                    break
            if not card or card.name != "li":
                card = link.parent
            text = card.get_text(" ", strip=True)

            if not text or "to let" not in text.lower():
                continue

            price = self._extract_price_pcm(text)
            beds = self._extract_beds(text)
            postcode = self._extract_postcode(text)
            avail = self._extract_available_date(text)

            # Clean up title: remove repetitive "To Let" / "Tenancy Info" etc
            title = re.sub(r"\s+Tenancy Info\s*", " ", text)
            title = re.sub(r"\s+Call Now:\s*[\d\s]+", "", title)

            results.append({
                "external_id": url,
                "url": url,
                "title": title[:120],
                "price_pcm": price,
                "beds": beds,
                "address": title[:100],
                "postcode": postcode,
                "available_date": avail,
            })

        # Enrich with detail page data (postcode, beds) for nearby-looking properties
        for lst in results:
            if not lst.get("postcode") or lst.get("beds") is None:
                self._enrich_from_detail(lst)

        # Method 2: fallback — parse from rendered text if no links found
        if not results:
            body = soup.get_text(" ", strip=True)
            for m in re.finditer(
                r"To Let\s+(.+?)\s+£\s*([\d,]+)\s*p\.?c\.?m",
                body, re.I,
            ):
                addr = m.group(1).strip()
                price = float(m.group(2).replace(",", ""))
                results.append({
                    "external_id": addr,
                    "url": self.SEARCH_URL,
                    "title": f"{addr} £{price:.0f}/pcm",
                    "price_pcm": price,
                    "beds": self._extract_beds(addr),
                    "address": addr,
                    "postcode": self._extract_postcode(addr),
                    "available_date": "",
                })

        return results

    def _enrich_from_detail(self, listing: dict) -> None:
        """Fetch detail page for postcode and bed count."""
        url = listing.get("url", "")
        if not url or url == self.SEARCH_URL:
            return
        try:
            import requests
            resp = requests.get(
                url,
                timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": config.USER_AGENT},
            )
            if resp.status_code != 200:
                return
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            body = soup.get_text(" ", strip=True)

            if not listing.get("postcode"):
                pc = listing.get("postcode") or self._extract_postcode(body)
                if pc:
                    listing["postcode"] = pc

            if listing.get("beds") is None:
                beds = self._extract_beds(body)
                if beds is not None:
                    listing["beds"] = beds

            if not listing.get("available_date"):
                avail = self._extract_available_date(body)
                if avail:
                    listing["available_date"] = avail
        except Exception as exc:
            logger.debug("[ClanGordon] Enrich error for %s: %s", url, exc)


class AlbanyLettingsScraper(OtherAgentsScraper):
    """Albany Lettings — Edinburgh letting agent."""
    SOURCE_NAME = "Albany Lettings"
    SEARCH_URL = "https://www.albanylettings.com/property-to-rent"
    EXTRACT_STRATEGY = "html"

    def fetch_listings(self) -> list[dict]:
        results = []
        seen = set()

        for page_num in [None, 2]:
            page_url = self.SEARCH_URL
            if page_num:
                page_url = f"{self.SEARCH_URL}/page-{page_num}"
            soup = self._soup(page_url)
            if soup is None:
                continue

            results_div = soup.find(class_="searchPage-results")
            if not results_div:
                continue

            text = results_div.get_text(" ", strip=True)

            # Collect unique property links from this page
            links = [
                f"https://www.albanylettings.com{a['href']}"
                for a in results_div.find_all("a", href=True)
                if a["href"].startswith("/") and a["href"].count("/") == 2
                and not a["href"].startswith("/page")
            ]
            # Deduplicate links while preserving order
            unique_links = list(dict.fromkeys(links))

            # Split by "£X / month" to get individual listings
            chunks = __import__("re").split(r"(?=To let)", text)

            link_idx = 0
            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk or "£" not in chunk:
                    continue
                if not any(x in chunk.lower() for x in ["bedroom", "bed", "flat", "studio"]):
                    continue

                url = unique_links[link_idx] if link_idx < len(unique_links) else self.SEARCH_URL
                link_idx += 1
                if url in seen:
                    continue
                seen.add(url)

                price_m = __import__("re").search(r"£\s*([\d,]+)\s*/?\s*month", chunk)
                price = float(price_m.group(1).replace(",", "")) if price_m else None

                bed_m = __import__("re").search(r"(\d+)\s*Bedroom", chunk, re.I)
                beds = int(bed_m.group(1)) if bed_m else None

                pc = self._extract_postcode(chunk)
                if not pc:
                    m = __import__("re").search(r"(?i)\b(EH\d{1,2})\b", chunk)
                    if m:
                        pc = m.group(1).upper()

                avail = self._extract_available_date(chunk)
                title = chunk[:120]

                results.append({
                    "external_id": url or chunk[:50],
                    "url": url,
                    "title": title,
                    "price_pcm": price,
                    "beds": beds,
                    "address": chunk[:100],
                    "postcode": pc,
                    "available_date": avail,
                })

        return results


class OpenRentScraper(OtherAgentsScraper):
    """OpenRent — UK's largest direct-letting platform."""
    SOURCE_NAME = "OpenRent"
    SEARCH_URL = "https://www.openrent.co.uk/properties-to-rent/edinburgh"
    EXTRACT_STRATEGY = "html"

    def fetch_listings(self) -> list[dict]:
        soup = self._soup(self.SEARCH_URL)
        if soup is None:
            return []

        results = []
        seen_urls = set()

        # Each card: <a class="pli search-property-card">
        for card in soup.select("a.pli.search-property-card"):
            href = card.get("href", "")
            if not href:
                continue
            url = href if href.startswith("http") else f"https://www.openrent.co.uk{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            text = card.get_text(" ", strip=True)
            if not text or "£" not in text:
                continue

            # Title: extract from card text
            title = text[:120]

            # Price: "£X per month" format
            price = self._extract_price_pcm(text)

            # Beds: from title text or URL slug
            beds = self._extract_beds(text)
            if beds is None:
                m = __import__("re").search(r"(\d)-bed", url.lower())
                if m:
                    beds = int(m.group(1))

            # Postcode
            postcode = self._extract_postcode(text)

            # Available date
            avail = self._extract_available_date(text)

            results.append({
                "external_id": url,
                "url": url,
                "title": title,
                "price_pcm": price,
                "beds": beds,
                "address": title[:80],
                "postcode": postcode,
                "available_date": avail,
            })

        return results

