#!/bin/bash
# Save as /Users/baijc/letting_agent/install_cron.sh
# Run: bash install_cron.sh

CRON_CMD="*/30 * * * * /Users/baijc/miniconda3/bin/python3 /Users/baijc/letting_agent/scrape_all.py >> /Users/baijc/letting_agent/cron.log 2>&1"

# Add to crontab (preserving existing entries)
(crontab -l 2>/dev/null | grep -v scrape_all.py; echo "$CRON_CMD") | crontab -

echo "✅ Cron job installed. Verifying:"
crontab -l | grep scrape_all
