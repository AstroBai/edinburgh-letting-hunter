#!/bin/bash
# Save as remove_cron.sh
# Run: bash remove_cron.sh

(crontab -l 2>/dev/null | grep -v scrape_all) | crontab -
echo "✅ Cron job removed."
