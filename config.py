"""
Configuration for the Edinburgh letting agent scraper.
Edit the EMAIL_* settings before running.
"""

# --- Target location ---
TARGET_POSTCODE = "EH9 2JG"
TARGET_LAT = 55.934767
TARGET_LON = -3.186329
RADIUS_MILES = 1.2
MAX_BEDS = 2  # ≤ this many bedrooms

# --- Email settings (Gmail SMTP) ---
# You MUST generate a Gmail App Password at:
#   https://myaccount.google.com/apppasswords
# (Requires 2FA enabled on your Google account.)
# Fill in the values below OR set env vars (safer, takes precedence).
EMAIL_FROM = "your-email@gmail.com"
EMAIL_TO = "your-email@gmail.com"
EMAIL_USERNAME = ""           # Your full Gmail address
EMAIL_APP_PASSWORD = ""       # The 16-char App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Alternatively set these env vars (takes precedence):
#   LETTING_AGENT_EMAIL_USER
#   LETTING_AGENT_EMAIL_PASS

# --- Data file ---
DB_PATH = "listings.db"

# --- Scraper settings ---
REQUEST_TIMEOUT = 30  # seconds
REQUEST_DELAY = 1.5   # seconds between requests to the same domain
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# --- Listing sources to scrape ---
# Each entry: (name, scraper_module, class_name, enabled)
# For JS-rendered sites (ESPC, Rettie, Umega) the headless scraper
# requires Playwright.  If not installed, those sources return zero
# listings without error.
SOURCES = [
    # Major portals (working)
    ("Citylets",           "scrapers.citylets",      "CityletsScraper",          True),
    ("SpareRoom",          "scrapers.spareroom",     "SpareRoomScraper",         True),
    # Major portals (needs Playwright for full JS rendering)
    ("ESPC",               "scrapers.headless",      "EspcHeadlessScraper",      True),
    # Other agencies from the Edinburgh Uni list
    ("s1homes",            "scrapers.other_agents",  "S1HomesScraper",           True),
    ("Belvoir",            "scrapers.other_agents",  "BelvoirScraper",           True),
    ("Northwood",          "scrapers.other_agents",  "NorthwoodScraper",         False),
    ("A Flat in Town",     "scrapers.other_agents",  "AFlatInTownScraper",       True),
    ("Dove Davies",        "scrapers.other_agents",  "DoveDaviesScraper",        True),
    ("Cornerstone",        "scrapers.other_agents",  "CornerstoneScraper",       True),
    ("Southside Mgmt",     "scrapers.other_agents",  "SouthsideMgmtScraper",     True),
    ("Edinburgh LC",       "scrapers.other_agents",  "EdinburghLettingCentreScraper", True),
    ("Glenham",            "scrapers.other_agents",  "GlenhamScraper",           True),
    ("Murray & Currie",    "scrapers.other_agents",  "FactotumScraper",          True),
    ("Clan Gordon",        "scrapers.other_agents",  "ClanGordonScraper",        True),
    ("Albany Lettings",    "scrapers.other_agents",  "AlbanyLettingsScraper",    True),
    ("OpenRent",           "scrapers.other_agents",  "OpenRentScraper",          True),
    ("DJ Alexander",       "scrapers.other_agents",  "DJAlexanderScraper",       True),
    # Disabled (Cloudflare / timeout):
    # ("Rettie",           "scrapers.headless",      "RettieHeadlessScraper",    False),
    # ("Umega",            "scrapers.headless",      "UmegaHeadlessScraper",     False),
]
