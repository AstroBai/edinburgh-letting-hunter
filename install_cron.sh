#!/bin/bash
# Save as install_cron.sh
# Run: bash install_cron.sh

CRON_CMD="*/30 * * * * cd /path/to/letting_agent && /usr/bin/python3 scrape_all.py >> cron.log 2>&1"

# Add to crontab (preserving existing entries)
(crontab -l 2>/dev/null | grep -v scrape_all.py; echo "$CRON_CMD") | crontab -

echo "✅ Cron job installed. Verifying:"
crontab -l | grep scrape_all
