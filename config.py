"""Global settings for the faculty scraper.

Every value here can also be overridden from the command line (see ``python main.py --help``).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------------------
# Output location
# --------------------------------------------------------------------------------------
# On Windows everything is written here by default. On other systems (or if this folder
# cannot be created) the scraper falls back to "<project>/output".
# You can also set the FACULTY_SCRAPER_OUTPUT environment variable or pass --output.
WINDOWS_OUTPUT_DIR = r"C:\Users\Hp\Downloads\Faculty Photo and Codes"


def default_output_dir() -> Path:
    env_dir = os.environ.get("FACULTY_SCRAPER_OUTPUT")
    if env_dir:
        return Path(env_dir)
    if os.name == "nt":
        return Path(WINDOWS_OUTPUT_DIR)
    return PROJECT_DIR / "output"


OUTPUT_DIR = default_output_dir()   # base folder for everything below
IMAGE_DIR_NAME = "photos"           # <OUTPUT_DIR>/photos/<University>/<Department>/<Name>.jpg
DATA_DIR_NAME = "data"              # <OUTPUT_DIR>/data/raw/*.csv and data/processed/*
LOG_DIR_NAME = "logs"               # <OUTPUT_DIR>/logs/scraper.log

# --------------------------------------------------------------------------------------
# HTTP behaviour (be polite!)
# --------------------------------------------------------------------------------------
REQUEST_DELAY = 1.5        # seconds between page requests to the same host
IMAGE_DELAY = 0.4          # seconds between image downloads from the same host
TIMEOUT = 25               # request timeout in seconds
MAX_RETRIES = 3            # retries for failed requests (with exponential back-off)
DOWNLOAD_WORKERS = 4       # parallel image downloads (still rate limited per host)

# Many university firewalls reject unknown user agents, so a normal browser UA is used.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

RESPECT_ROBOTS_TXT = True           # skip URLs that robots.txt disallows
# Several university sites ship broken/expired TLS certificates. When True, a host that
# fails certificate verification is retried without verification (a warning is logged).
ALLOW_INSECURE_SSL_FALLBACK = True

# --------------------------------------------------------------------------------------
# Crawling
# --------------------------------------------------------------------------------------
DISCOVERY_DEPTH = 2               # how many clicks away from the start pages to look for faculty lists
MAX_PAGES_PER_UNIVERSITY = 350    # hard cap on HTML pages fetched per university
MAX_PAGINATION_PAGES = 40         # cap on "next page" hops for one faculty list
# Visit individual profile pages? "auto" = only when the list has no photo for a person,
# "always" = every profile (slower, but gets the largest photo), "never" = list pages only.
VISIT_PROFILES = "auto"
# Render JavaScript pages with a headless browser (Chrome/Edge/Firefox via Selenium)?
# "auto" = only when a page looks empty without JavaScript, True = always, False = never.
USE_SELENIUM = "auto"
SELENIUM_PAGE_WAIT = 4            # seconds to let a rendered page settle
SKIP_NON_ACADEMIC_STAFF = True    # ignore officers/lab staff that some "faculty & staff" pages list

# --------------------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------------------
DOWNLOAD_IMAGES = True       # download faculty photos (use --no-images to only build the dataset)
CONVERT_TO_JPG = False       # convert every photo to .jpg (otherwise the original format is kept)
MIN_IMAGE_BYTES = 1500       # smaller files are icons/placeholders, not photos
MIN_IMAGE_SIDE = 60          # pixels; smaller images are icons
# If the exact same picture is used for this many different people it is a
# "no photo" placeholder and is deleted instead of being saved under their names.
PLACEHOLDER_REPEAT_THRESHOLD = 3

# --------------------------------------------------------------------------------------
# Stand-alone scripts (DIU, UIU, AIUB, IUB, NSU in external_scrapers/)
# --------------------------------------------------------------------------------------
# False = their photos go to <OUTPUT_DIR>/photos/<University>/ like everything else.
# True  = each script saves to the folder written inside the script itself.
EXTERNAL_SCRIPTS_OWN_OUTPUT = False
