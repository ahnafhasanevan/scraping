
"""
NSU Faculty Photo Downloader
============================
Visits every department's faculty page on North South University's website
and downloads each faculty member's photo.

Sources:
  * https://www.northsouth.edu/faculty-members/...   (17 departments, card layout)
  * https://ece.northsouth.edu/people/type/faculty/  (Electrical & Computer Eng. --
    the main site just links out to this separate website, which uses a table layout)

Install once:   pip install requests beautifulsoup4
Run:            python nsu_faculty_photos.py
"""

import csv
import os
import re
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit, quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============================================================================
#  SETTINGS  -- change these to suit you
# =============================================================================

# Where to save everything.
# Default: a folder called "nsu_faculty_photos" next to this script.
# To use your own folder, replace the whole line with a path, e.g.
#   SAVE_DIR = r"D:\NSU\faculty_photos"          (Windows -- keep the r before the quotes)
#   SAVE_DIR = "/Users/yourname/Desktop/faculty"  (Mac / Linux)
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # e.g. running inside a notebook
    _HERE = os.getcwd()
SAVE_DIR = os.path.join(_HERE, r"C:\Users\Hp\Downloads\NSU Faculty Photos")

# Only scrape some departments? Put their keys here, e.g. ["ece", "eml"].
# Leave as [] to scrape ALL departments. (Keys are in the DEPARTMENTS list below.)
ONLY_DEPARTMENTS = []

# Many faculty have no real photo and the site shows a grey "default" picture.
# True  = don't download those placeholders (they are listed as "placeholder_skipped" in the CSV)
# False = download them too
SKIP_PLACEHOLDERS = True

# If a photo file already exists, don't download it again (lets you re-run safely).
SKIP_EXISTING = True

DELAY_SECONDS = 0.5     # pause between requests (be polite to the server)
TIMEOUT_SECONDS = 30    # give up on a single request after this long
MAX_PAGES = 60          # safety limit on pagination per department

# =============================================================================
#  DEPARTMENTS  (verified against https://www.northsouth.edu/faculty-members/)
#  (key, folder name, page url, layout)
# =============================================================================
BASE = "https://www.northsouth.edu/faculty-members"
DEPARTMENTS = [
    # School of Humanities & Social Sciences
    ("eml",     "SHSS_English_and_Modern_Languages",        f"{BASE}/shss/eml/",                "nsu"),
    ("pss",     "SHSS_Political_Science_and_Sociology",     f"{BASE}/shss/pss/",                "nsu"),
    ("history", "SHSS_History_and_Philosophy",              f"{BASE}/shss/history-philosophy/", "nsu"),
    ("law",     "SHSS_Law",                                 f"{BASE}/shss/law/",                "nsu"),
    ("mcj",     "SHSS_Media_Communication_and_Journalism",  f"{BASE}/shss/faculty-mcj/",        "nsu"),
    # School of Business & Economics
    ("accfin",  "SBE_Accounting_and_Finance",               f"{BASE}/sbe/acc-fin/",             "nsu"),
    ("mib",     "SBE_Marketing_and_International_Business", f"{BASE}/sbe/marketing-ib/",        "nsu"),
    ("mgt",     "SBE_Management",                           f"{BASE}/sbe/mgt/",                 "nsu"),
    ("eco",     "SBE_Economics",                            f"{BASE}/sbe/economics/",           "nsu"),
    # School of Health & Life Sciences
    ("bbt",     "SHLS_Biochemistry_and_Biotechnology",      f"{BASE}/shls/bbt/",                "nsu"),
    ("pbh",     "SHLS_Public_Health",                       f"{BASE}/shls/pbh/",                "nsu"),
    ("pharmacy", "SHLS_Pharmaceutical_Sciences",            f"{BASE}/shls/pharmacy/",           "nsu"),
    ("esm",     "SHLS_Environmental_Science_and_Management", f"{BASE}/shls/esm/",               "nsu"),
    ("mic",     "SHLS_Microbiology",                        f"{BASE}/shls/mic/",                "nsu"),
    # School of Engineering & Physical Sciences
    ("ece",     "SEPS_Electrical_and_Computer_Engineering", "https://ece.northsouth.edu/people/type/faculty/", "ece"),
    ("cee",     "SEPS_Civil_and_Environmental_Engineering", f"{BASE}/seps/cee/",                "nsu"),
    ("mathphy", "SEPS_Mathematics_and_Physics",             f"{BASE}/seps/mathematics-physics/", "nsu"),
    ("arch",    "SEPS_Architecture",                        f"{BASE}/seps/architecture/",       "nsu"),
]

# Image URLs containing any of these are the site's grey "no photo" placeholders.
PLACEHOLDER_KEYWORDS = ["default-faculty", "default_faculty"]

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/pjpeg": ".jpg",
    "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "image/bmp": ".bmp", "image/tiff": ".tif",
}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# =============================================================================
#  HELPERS
# =============================================================================
def log(msg=""):
    print(msg, flush=True)


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    retry = Retry(
        total=4,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_soup(session, url):
    """Download a page and return a BeautifulSoup object (or None on failure)."""
    try:
        resp = session.get(url, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        log(f"    ! Could not load {url}\n      {exc}")
        return None
    if resp.status_code != 200:
        log(f"    ! HTTP {resp.status_code} for {url}")
        return None
    return BeautifulSoup(resp.content, "html.parser")


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def safe_filename(name):
    """Make a string safe to use as a file name on Windows / Mac / Linux."""
    name = clean_text(name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = name.strip(" .")
    return name[:120] or "unknown"


def unique_stem(stem, used):
    candidate, n = stem, 2
    while candidate.lower() in used:
        candidate = f"{stem}_{n}"
        n += 1
    used.add(candidate.lower())
    return candidate


def clean_image_url(raw, base_url):
    """Make an absolute URL and percent-encode spaces etc. in the path.
    (The site has image names such as '5-8597.DSC_4833 (3).JPG' with spaces.)"""
    absolute = urljoin(base_url, raw.strip())
    parts = urlsplit(absolute)
    path = quote(parts.path, safe="/%:@!$&'()*+,;=~-._")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def url_variants(url):
    """The site has a few odd URLs ('//newassets/...', repeated folders).
    Try the URL as-is first, then a tidied-up version."""
    variants = [url]
    parts = urlsplit(url)
    path = re.sub(r"/{2,}", "/", parts.path)
    path = path.replace("/newassets/images/newassets/images/", "/newassets/images/")
    tidy = urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))
    if tidy not in variants:
        variants.append(tidy)
    return variants


def pick_img_src(img):
    """Return the real image address (handles lazy-loading attributes)."""
    for attr in ("data-src", "data-original", "data-lazy-src", "data-lazy", "src"):
        value = (img.get(attr) or "").strip()
        if value and not value.startswith("data:"):
            return value
    return ""


def is_placeholder(url):
    low = url.lower()
    return any(key in low for key in PLACEHOLDER_KEYWORDS)


def extension_for(url, content_type):
    ext = os.path.splitext(urlsplit(url).path)[1].lower()
    if ext in IMG_EXTS:
        return ext
    return CONTENT_TYPE_EXT.get(content_type, ".jpg")


def download_image(session, img_url, dest_dir, stem):
    """Try to download the image. Returns (status, saved_path)."""
    last_error = "unknown error"
    for candidate in url_variants(img_url):
        try:
            resp = session.get(candidate, timeout=TIMEOUT_SECONDS, stream=True)
        except requests.RequestException as exc:
            last_error = str(exc)[:120]
            continue
        try:
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            url_ext = os.path.splitext(urlsplit(candidate).path)[1].lower()
            looks_like_image = ctype.startswith("image/") or (
                ctype in ("application/octet-stream", "binary/octet-stream") and url_ext in IMG_EXTS
            )
            if not looks_like_image:
                last_error = f"not an image (Content-Type: {ctype or 'none'})"
                continue
            path = os.path.join(dest_dir, stem + extension_for(candidate, ctype))
            with open(path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            return "downloaded", path
        finally:
            resp.close()
    return f"failed: {last_error}", ""


# =============================================================================
#  PARSER 1 -- www.northsouth.edu department pages (card layout, ?page=N)
# =============================================================================
def find_last_page(soup, dept_path):
    """Read the highest ?page=N number from the pagination links."""
    highest = 1
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if dept_path not in urlsplit(href).path:
            continue
        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def parse_nsu_page(soup, page_url, dept_url):
    """Return a list of {'name', 'profile_url', 'img_src'} for one page."""
    dept_path = urlsplit(dept_url).path.rstrip("/")

    def is_profile(href):
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            return False
        parts = urlsplit(urljoin(page_url, href))
        return (
            parts.netloc.lower().endswith("northsouth.edu")
            and not parts.query
            and parts.path.rstrip("/").startswith(dept_path + "/")
        )

    def find_card_img(a_tag):
        """Climb up from the profile link until we find the <img> of the same card."""
        node = a_tag
        for _ in range(8):
            if node is None or node.name in ("body", "html", "[document]"):
                return None
            hrefs = {
                urljoin(page_url, x["href"])
                for x in node.find_all("a", href=True)
                if is_profile(x["href"])
            }
            if len(hrefs) > 1:      # we climbed too far (into the whole grid)
                return None
            img = node.find("img")
            if img is not None and pick_img_src(img):
                return img
            node = node.parent
        return None

    cards = {}
    for a in soup.find_all("a", href=True):
        if not is_profile(a["href"]):
            continue
        profile_url = urljoin(page_url, a["href"].strip())
        card = cards.setdefault(profile_url, {"name": "", "profile_url": profile_url, "img": None})
        text = clean_text(a.get_text(" ", strip=True))
        if text and not card["name"]:
            card["name"] = text
        if card["img"] is None:
            card["img"] = find_card_img(a)

    results = []
    for card in cards.values():
        img = card["img"]
        name = card["name"] or (clean_text(img.get("alt", "")) if img is not None else "")
        results.append({
            "name": name,
            "profile_url": card["profile_url"],
            "img_src": pick_img_src(img) if img is not None else "",
        })
    return results


def scrape_nsu_department(session, dept_url):
    dept_path = urlsplit(dept_url).path
    people, seen = [], set()
    page, last_page = 1, 1
    while page <= min(last_page, MAX_PAGES):
        url = dept_url if page == 1 else f"{dept_url}?page={page}"
        soup = get_soup(session, url)
        if soup is None:
            break
        last_page = max(last_page, find_last_page(soup, dept_path))
        found = [p for p in parse_nsu_page(soup, url, dept_url) if p["profile_url"] not in seen]
        log(f"    page {page}/{last_page}: {len(found)} faculty")
        if not found:
            break
        for p in found:
            seen.add(p["profile_url"])
            p["page_url"] = url
            people.append(p)
        page += 1
        time.sleep(DELAY_SECONDS)
    return people


# =============================================================================
#  PARSER 2 -- ece.northsouth.edu (table layout, ?page=N)
# =============================================================================
def parse_ece_page(soup, page_url):
    results = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        info = cells[1]
        strong = info.find(["strong", "b"])
        name = clean_text(strong.get_text(" ", strip=True)) if strong else ""
        if not name:
            continue                      # header row / empty row
        profile_url = ""
        for a in info.find_all("a", href=True):
            if clean_text(a.get_text()).lower() == "profile":
                profile_url = urljoin(page_url, a["href"].strip())
                break
        img = cells[0].find("img")
        results.append({
            "name": name,
            "profile_url": profile_url or f"ece:{name}",
            "img_src": pick_img_src(img) if img is not None else "",
        })
    return results


def scrape_ece_department(session, dept_url):
    people, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{dept_url}?page={page}"
        soup = get_soup(session, url)
        if soup is None:
            break
        found = [p for p in parse_ece_page(soup, url) if p["profile_url"] not in seen]
        log(f"    page {page}: {len(found)} faculty")
        if not found:                     # empty or repeated page -> we're past the end
            break
        for p in found:
            seen.add(p["profile_url"])
            p["page_url"] = url
            people.append(p)
        time.sleep(DELAY_SECONDS)
    return people


# =============================================================================
#  MAIN
# =============================================================================
def process_department(session, key, folder, dept_url, layout, csv_rows):
    dept_dir = os.path.join(SAVE_DIR, folder)
    os.makedirs(dept_dir, exist_ok=True)

    people = scrape_ece_department(session, dept_url) if layout == "ece" \
        else scrape_nsu_department(session, dept_url)

    existing = {os.path.splitext(f)[0].lower() for f in os.listdir(dept_dir)}
    used = set()
    counts = {"found": len(people), "downloaded": 0, "existing": 0,
              "placeholder": 0, "no_image": 0, "failed": 0}

    if not people:
        log("    ! No faculty found on this department page "
            "(page may have changed, or it links to another site).")

    for person in people:
        name = person["name"] or "unknown"
        stem = unique_stem(safe_filename(name), used)
        row = {"department": folder, "name": name, "profile_url": person["profile_url"],
               "image_url": "", "saved_file": "", "status": ""}

        if not person["img_src"]:
            row["status"] = "no_image"
            counts["no_image"] += 1
        else:
            img_url = clean_image_url(person["img_src"], person["page_url"])
            row["image_url"] = img_url
            if SKIP_PLACEHOLDERS and is_placeholder(img_url):
                row["status"] = "placeholder_skipped"
                counts["placeholder"] += 1
            elif SKIP_EXISTING and stem.lower() in existing:
                row["status"] = "skipped_exists"
                counts["existing"] += 1
            else:
                status, path = download_image(session, img_url, dept_dir, stem)
                row["status"] = status
                if status == "downloaded":
                    row["saved_file"] = os.path.relpath(path, SAVE_DIR)
                    counts["downloaded"] += 1
                    log(f"      saved: {os.path.basename(path)}")
                else:
                    counts["failed"] += 1
                    log(f"      FAILED: {name} -> {status}")
                time.sleep(DELAY_SECONDS)
        csv_rows.append(row)
    return counts


def main():
    try:  # avoid Windows console crashes on unusual characters
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    save_dir = os.path.abspath(os.path.expanduser(SAVE_DIR))
    globals()["SAVE_DIR"] = save_dir
    os.makedirs(save_dir, exist_ok=True)

    wanted = {k.lower() for k in ONLY_DEPARTMENTS}
    selected = [d for d in DEPARTMENTS if not wanted or d[0] in wanted]
    unknown = wanted - {d[0] for d in DEPARTMENTS}
    if unknown:
        log(f"Unknown department key(s) ignored: {', '.join(sorted(unknown))}")
    if not selected:
        log("Nothing to do -- check ONLY_DEPARTMENTS.")
        return

    log(f"Saving to: {save_dir}")
    log(f"Departments to scrape: {len(selected)}\n")

    session = make_session()
    csv_rows, summary = [], []
    try:
        for i, (key, folder, url, layout) in enumerate(selected, 1):
            log(f"[{i}/{len(selected)}] {folder}  ({url})")
            counts = process_department(session, key, folder, url, layout, csv_rows)
            summary.append((folder, counts))
            log("")
    except KeyboardInterrupt:
        log("\nInterrupted by user -- saving what we have so far...")
    finally:
        csv_path = os.path.join(save_dir, "faculty_photos_index.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["department", "name", "profile_url", "image_url", "saved_file", "status"])
            writer.writeheader()
            writer.writerows(csv_rows)

    log("=" * 78)
    log(f"{'Department':<46}{'found':>6}{'saved':>7}{'had':>5}{'default':>8}{'none':>6}{'fail':>6}")
    log("-" * 78)
    totals = {k: 0 for k in ("found", "downloaded", "existing", "placeholder", "no_image", "failed")}
    for folder, c in summary:
        log(f"{folder:<46}{c['found']:>6}{c['downloaded']:>7}{c['existing']:>5}"
            f"{c['placeholder']:>8}{c['no_image']:>6}{c['failed']:>6}")
        for k in totals:
            totals[k] += c[k]
    log("-" * 78)
    log(f"{'TOTAL':<46}{totals['found']:>6}{totals['downloaded']:>7}{totals['existing']:>5}"
        f"{totals['placeholder']:>8}{totals['no_image']:>6}{totals['failed']:>6}")
    log("=" * 78)
    log("saved = newly downloaded | had = already on disk | default = site placeholder skipped")
    log("none = no photo on page | fail = download error (see CSV for details)")
    log(f"\nIndex file: {csv_path}")


if __name__ == "__main__":
    main()
