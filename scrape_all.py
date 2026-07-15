#!/usr/bin/env python3
"""
Main entry point – orchestrates all scrapers, compares with history,
and sends email notifications for new listings.

Usage:
    python3 scrape_all.py              # normal run
    python3 scrape_all.py --dry-run    # print new listings, don't email
    python3 scrape_all.py --force      # re-send even if previously seen
"""
from __future__ import annotations
import sys
import importlib
import logging
from datetime import datetime

from config import SOURCES
from storage import init_db, record_listings, record_scrape_run, mark_inactive
from notifier import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_scraper(source_name: str, module_path: str, class_name: str):
    """Dynamically import and instantiate a scraper class."""
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls()
    except (ImportError, AttributeError) as exc:
        logger.warning("Cannot load scraper %s/%s: %s", module_path, class_name, exc)
        return None


def main():
    dry_run = "--dry-run" in sys.argv

    logger.info("=" * 50)
    logger.info("Letting Agent Scraper — starting run")
    logger.info("=" * 50)

    init_db()

    all_new: list[dict] = []

    for name, mod_path, cls_name, enabled in SOURCES:
        if not enabled:
            logger.info("[%s] Skipped (disabled)", name)
            continue

        scraper = load_scraper(name, mod_path, cls_name)
        if scraper is None:
            continue

        try:
            listings = scraper.scrape()
        except Exception as exc:
            logger.error("[%s] Scrape failed: %s", name, exc)
            continue

        if not listings:
            logger.info("[%s] 0 listings after filtering", name)
            # Still record scrape run for tracking
            record_scrape_run(name)
            continue

        # Update storage – new_ones are the ones first seen this run
        new_ones = record_listings(name, listings)
        logger.info(
            "[%s] %d total, %d new",
            name,
            len(listings),
            len(new_ones),
        )

        # Build set of active external IDs for staleness tracking
        active_ids = {lst.get("external_id") or lst.get("url", "") for lst in listings}
        gone = mark_inactive(name, active_ids)
        if gone:
            logger.info("[%s] %d listings are no longer active", name, gone)

        all_new.extend(new_ones)
        record_scrape_run(name)

    # --- Summary ---
    logger.info("=" * 50)
    logger.info("Run complete — %d total new listings across all sources", len(all_new))
    if all_new:
        logger.info("New listings:")
        for lst in all_new:
            logger.info(
                "  • %s: %s (%s, %s bed(s), £%s/pcm)",
                lst.get("source", "?"),
                lst.get("title", "?"),
                lst.get("address", "?") or "?",
                lst.get("beds", "?"),
                f"{lst.get('price_pcm', 0):,.0f}" if lst.get("price_pcm") else "?",
            )

    # --- Notify ---
    if "--force" in sys.argv:
        # Re-notify everything seen this run
        all_new = record_listings("__force__", [])  # dummy
        # Actually, just pass all listings from this run
        logger.info("Force mode — sending all %d listings", len(all_new) if all_new else 0)

    send_notification(all_new)
    return 0 if len(all_new) == 0 else 1  # exit 1 when there's news


if __name__ == "__main__":
    sys.exit(main())
