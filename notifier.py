"""
Email notification via Gmail SMTP.
Falls back to printing to console when credentials are missing.
"""
from __future__ import annotations

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def _get_creds() -> tuple[str, str]:
    """(username, app_password) – env vars override config file."""
    user = os.environ.get("LETTING_AGENT_EMAIL_USER") or config.EMAIL_USERNAME or config.EMAIL_FROM
    pw = os.environ.get("LETTING_AGENT_EMAIL_PASS") or config.EMAIL_APP_PASSWORD
    return user, pw


def _build_html(new_listings: list[dict]) -> str:
    """Turn new listings into a tidy HTML table."""
    if not new_listings:
        return "<p>No new listings found.</p>"

    # Cross-source dedup: same postcode + same price (±5%) = same property
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for lst in sorted(
        new_listings,
        key=lambda x: float("inf") if x.get("price_pcm") is None else x["price_pcm"],
    ):
        pc = lst.get("postcode", "") or ""
        price = lst.get("price_pcm")
        if not pc and price is None:
            deduped.append(lst)
            continue
        if pc and price is not None:
            # Round price to nearest £50 for matching
            bucket = round(price / 50) * 50
            key = (pc.split()[0] if pc else "", bucket)
        elif pc:
            key = (pc.split()[0] if pc else "", -1)
        else:
            key = ("", round(price / 50) * 50) if price else None
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(lst)

    rows = ""
    for lst in deduped:
        beds = lst.get("beds", "?")
        price = lst.get("price_pcm")
        price_str = f"£{price:,.0f}/pcm" if price else "—"
        title = lst.get("title") or "Untitled"
        address = lst.get("address") or ""
        postcode = lst.get("postcode") or ""
        url = lst.get("url", "")
        source = lst.get("source", "unknown")
        avail = lst.get("available_date", "") or ""
        loc = f"{address}, {postcode}".strip(", ")
        title_link = f'<a href="{url}">{title}</a>'
        avail_display = f"<small>{avail}</small>" if avail else ""
        rows += f"""
        <tr>
            <td>{source}</td>
            <td>{title_link}<br>{avail_display}</td>
            <td>{beds}</td>
            <td style="white-space:nowrap">{price_str}</td>
            <td>{loc}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
tr:nth-child(even) {{ background: #fafafa; }}
</style></head>
<body>
<h2>🏠 New Rental Properties Found</h2>
<p>Listings within {config.RADIUS_MILES} mile(s) of {config.TARGET_POSTCODE}
   — ≤{config.MAX_BEDS} bed(s) — rental only.</p>
<table><thead><tr>
    <th>Source</th><th>Title</th><th>Beds</th><th>Price</th><th>Location</th>
</tr></thead><tbody>
{rows}
</tbody></table>
<p><small>Scanned at {datetime.now().strftime("%Y-%m-%d %H:%M")}</small></p>
</body></html>"""


def send_notification(new_listings: list[dict]) -> bool:
    """Send an email with new listings.  Returns True on success.

    If email credentials are not configured, prints to console instead.
    """
    if not new_listings:
        logger.info("No new listings — skipping notification.")
        # Still print for cron logging
        print(f"[{datetime.now():%H:%M}] No new listings found.")
        return True

    user, pw = _get_creds()

    if not pw:
        # Dry-run mode: print to console
        # Cross-source dedup
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for lst in sorted(
            new_listings,
            key=lambda x: float("inf") if x.get("price_pcm") is None else x["price_pcm"],
        ):
            pc = lst.get("postcode", "") or ""
            price = lst.get("price_pcm")
            if not pc and price is None:
                deduped.append(lst)
                continue
            key = None
            if pc and price is not None:
                bucket = round(price / 50) * 50
                key = (pc.split()[0] if pc else "", bucket)
            elif pc:
                key = (pc.split()[0] if pc else "", -1)
            elif price is not None:
                key = ("", round(price / 50) * 50)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            deduped.append(lst)

        print("=" * 60)
        print(f"🔔 {len(deduped)} NEW LISTING(S) FOUND (deduped, sorted by price)")
        print("=" * 60)
        for lst in deduped:
            price = lst.get("price_pcm")
            price_str = f"£{price:,.0f}/pcm" if price else "—"
            avail = lst.get("available_date", "") or ""
            beds = lst.get("beds", "?")
            print(f"  {price_str:>10s} | {lst.get('source','?'):15s} | {beds} bed(s) | {avail}")
            print(f"           {lst.get('title','?')[:60]}")
            print(f"           {lst.get('url','')}")
            print()
        return True

    # Dedup again for email
    seen: set[tuple] = set()
    email_list: list[dict] = []
    for lst in sorted(
        new_listings,
        key=lambda x: float("inf") if x.get("price_pcm") is None else x["price_pcm"],
    ):
        pc = lst.get("postcode", "") or ""; price = lst.get("price_pcm")
        key = None
        if pc and price is not None:
            key = (pc.split()[0] if pc else "", round(price / 50) * 50)
        elif pc:
            key = (pc.split()[0] if pc else "", -1)
        elif price is not None:
            key = ("", round(price / 50) * 50)
        if key and key in seen: continue
        if key: seen.add(key)
        email_list.append(lst)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 {len(email_list)} New Rental {'Property' if len(email_list)==1 else 'Properties'} Near {config.TARGET_POSTCODE}"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    msg.attach(MIMEText(_build_html(email_list), "html"))

    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(user, pw)
            server.send_message(msg)
        logger.info("Notification email sent to %s", config.EMAIL_TO)
        print(f"[{datetime.now():%H:%M}] ✅ Email sent to {config.EMAIL_TO}")
        return True
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        print(f"[{datetime.now():%H:%M}] ❌ Email failed: {exc}")
        return False
