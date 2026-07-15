# Edinburgh Letting Agent Scraper 🏠

> **⚠️ Disclaimer**
>
> This code is provided for **personal learning and automated property search** purposes only. Users are expected to:
> - Comply with each target website's Terms of Service
> - Respect `robots.txt` rules
> - Set reasonable request intervals to avoid overloading servers
> - Accept all risks associated with using this code
>
> The author does not endorse or support any illegal or commercial use of this code.
> If a website explicitly prohibits automated access, please stop scraping that site.

Scrapes property letting websites and SpareRoom for rental properties near **EH9 2XX** (Morningside, Edinburgh), and emails new listings every 30 minutes.

## Quick Start

### 1. Configure email credentials

Open `config.py` and set your Gmail App Password:

```python
EMAIL_FROM = "your-email@gmail.com"
EMAIL_TO = "your-email@gmail.com"
EMAIL_USERNAME = "your-email@gmail.com"
EMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"  # 16-char Gmail App Password
```

**How to get a Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords
2. Requires 2-Step Verification enabled
3. Generate a 16-character app password
4. Paste it into `config.py`

**OR** set env vars (more secure):
```bash
export LETTING_AGENT_EMAIL_USER="your-email@gmail.com"
export LETTING_AGENT_EMAIL_PASS="your-app-password"
```

### 2. Test the scraper

```bash
cd /path/to/letting_agent
python3 scrape_all.py --dry-run
```

This will print all new listings without emailing.

### 3. Install the cron job (every 30 min)

```bash
python3 setup_cron.py install
```

Or install manually:
```bash
crontab -l > /tmp/my_cron 2>/dev/null
echo "*/30 * * * * cd /path/to/letting_agent && /usr/bin/python3 scrape_all.py >> cron.log 2>&1" >> /tmp/my_cron
crontab /tmp/my_cron
rm /tmp/my_cron
```

### 4. (Optional) Install Playwright for JS-rendered sites

ESPC, Rettie, and Umega require JavaScript rendering.
Without Playwright, only **Citylets** and **SpareRoom** are scraped.

```bash
pip3 install playwright
playwright install chromium
```

## What it does

Every 30 minutes, the system:
1. **Scrapes** property websites for rentals
2. **Filters** to ≤2 beds within ~1 mile of EH9 2XX
3. **Compares** with previously seen listings (SQLite DB)
4. **Emails** you only when new listings appear

## Supported sources

| Source | Status | Requires |
|--------|--------|----------|
| Citylets | ✅ Working | - |
| SpareRoom | ✅ Working | - |
| ESPC | ⏳ Needs Playwright | `pip3 install playwright` |
| Rettie | ⏳ Needs Playwright | `pip3 install playwright` |
| Umega | ⏳ Needs Playwright | `pip3 install playwright` |

## Configuration

Edit `config.py` to change:
- `RADIUS_MILES` – search radius from EH9 2XX (default: 1.0)
- `MAX_BEDS` – max bedrooms (default: 2)
- `SOURCES` – enable/disable specific scrapers
- `EMAIL_*` – notification settings

## Files

```
letting_agent/
├── config.py          # Settings (edit this!)
├── scrape_all.py      # Main entry point
├── storage.py         # SQLite database
├── notifier.py        # Email sender
├── geocode.py         # Postcode lookups & distance calc
├── setup_cron.py      # Cron job manager
├── requirements.txt   # Python dependencies
├── scrapers/
│   ├── base.py        # Base scraper class
│   ├── citylets.py    # Citylets.co.uk
│   ├── spareroom.py   # SpareRoom.co.uk
│   └── headless.py    # Playwright-based scrapers
└── listings.db        # Auto-created SQLite DB
```
