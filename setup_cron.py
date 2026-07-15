#!/usr/bin/env python3
"""
Install or remove the crontab entry to run scrape_all.py every 30 minutes.

Usage:
    python3 setup_cron.py install     # add to crontab
    python3 setup_cron.py remove      # remove from crontab
    python3 setup_cron.py status      # check current status
"""
from __future__ import annotations
import sys
import subprocess
import os

CRON_COMMENT = "# letting-agent-scraper (every 30 min)"
SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "scrape_all.py")
)
CRON_LINE = f"*/30 * * * * cd {os.path.dirname(SCRIPT)} && {sys.executable} {SCRIPT} >> {os.path.dirname(SCRIPT)}/cron.log 2>&1"


def get_crontab() -> list[str]:
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.splitlines()
    except FileNotFoundError:
        pass
    return []


def set_crontab(lines: list[str]) -> None:
    text = "\n".join(lines) + "\n" if lines else ""
    proc = subprocess.run(
        ["crontab", "-"],
        input=text, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        print(f"❌ Failed to update crontab: {proc.stderr.strip()}")
        sys.exit(1)


def cmd_install() -> None:
    current = get_crontab()
    # Remove old entries from this tool
    filtered = [
        l for l in current
        if CRON_COMMENT not in l and not l.strip().endswith("scrape_all.py")
    ]
    filtered.append(CRON_COMMENT)
    filtered.append(CRON_LINE)
    set_crontab(filtered)
    print(f"✅ Installed cron job (every 30 min):")
    print(f"   {CRON_LINE}")
    print(f"   Logs → {os.path.dirname(SCRIPT)}/cron.log")


def cmd_remove() -> None:
    current = get_crontab()
    filtered = [
        l for l in current
        if CRON_COMMENT not in l and "scrape_all.py" not in l
    ]
    set_crontab(filtered)
    print("✅ Removed letting-agent-scraper cron job")


def cmd_status() -> None:
    current = get_crontab()
    entries = [l for l in current if "scrape_all.py" in l]
    if entries:
        print("✅ Cron job is installed:")
        for e in entries:
            print(f"   {e}")
    else:
        print("ℹ️  No cron job installed for letting-agent-scraper")
        print(f"   Run `python3 setup_cron.py install` to add one")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 setup_cron.py [install|remove|status]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "install":
        cmd_install()
    elif command == "remove":
        cmd_remove()
    elif command == "status":
        cmd_status()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
