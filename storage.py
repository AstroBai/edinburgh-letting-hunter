"""
SQLite-backed storage for seen listings.  Prevents duplicate notifications.
"""
from __future__ import annotations
import sqlite3
import json
import threading
from datetime import datetime
from typing import Iterable

from config import DB_PATH

_LOCAL = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Thread-local connection."""
    if not hasattr(_LOCAL, "conn") or _LOCAL.conn is None:
        _LOCAL.conn = sqlite3.connect(DB_PATH)
        _LOCAL.conn.row_factory = sqlite3.Row
    return _LOCAL.conn


_SCRAPE_HEADER = """
CREATE TABLE IF NOT EXISTS scrapes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT    NOT NULL,
    source      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    external_id TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    title       TEXT,
    price_pcm   REAL,
    beds        INTEGER,
    address     TEXT,
    postcode    TEXT,
    latitude    REAL,
    longitude   REAL,
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(source, is_active);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen);
"""


def init_db() -> None:
    conn = _get_conn()
    conn.executescript(_SCRAPE_HEADER)
    conn.commit()


def _listing_exists(source: str, external_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "SELECT 1 FROM listings WHERE source = ? AND external_id = ?",
        (source, external_id),
    )
    return cur.fetchone() is not None


def record_listings(source: str, listings: list[dict]) -> list[dict]:
    """Insert/update listings in bulk.

    Returns the subset of *listings* that are genuinely NEW (first time seen).
    """
    conn = _get_conn()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    new_ones: list[dict] = []

    for listing in listings:
        ext_id = listing.get("external_id") or listing.get("url", "")
        if not ext_id:
            continue

        exists = _listing_exists(source, ext_id)
        if not exists:
            conn.execute(
                """INSERT OR IGNORE INTO listings
                   (source, external_id, url, title, price_pcm, beds,
                    address, postcode, latitude, longitude,
                    first_seen, last_seen, is_active)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    source,
                    ext_id,
                    listing.get("url", ""),
                    listing.get("title"),
                    listing.get("price_pcm"),
                    listing.get("beds"),
                    listing.get("address"),
                    listing.get("postcode"),
                    listing.get("latitude"),
                    listing.get("longitude"),
                    now,
                    now,
                ),
            )
            new_ones.append(listing)
        else:
            # Update last_seen
            conn.execute(
                "UPDATE listings SET last_seen = ?, is_active = 1 "
                "WHERE source = ? AND external_id = ?",
                (now, source, ext_id),
            )
    conn.commit()
    return new_ones


def mark_inactive(source: str, active_external_ids: set[str]) -> int:
    """Mark listings no longer present as inactive.  Returns count."""
    conn = _get_conn()
    cur = conn.execute(
        "SELECT external_id FROM listings WHERE source = ? AND is_active = 1",
        (source,),
    )
    known = {row["external_id"] for row in cur.fetchall()}
    gone = known - active_external_ids
    for ext_id in gone:
        conn.execute(
            "UPDATE listings SET is_active = 0 WHERE source = ? AND external_id = ?",
            (source, ext_id),
        )
    conn.commit()
    return len(gone)


def record_scrape_run(source: str) -> None:
    conn = _get_conn()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    conn.execute("INSERT INTO scrapes (run_at, source) VALUES (?, ?)", (now, source))
    conn.commit()
