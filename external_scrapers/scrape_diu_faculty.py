"""
Daffodil International University (DIU) Faculty Photo Scraper
==============================================================
Downloads the photo of every faculty member, for every department, from the
DIU faculty portal:
    https://faculty.daffodilvarsity.edu.bd/

How the site is organised (and how this script handles it)
-----------------------------------------------------------
1. The portal HOMEPAGE lists every faculty and every department under it
   (each department links to /teachers/<slug>.html). The script reads that
   list itself, so new departments are picked up automatically.
2. Each department page lists its teachers 20 at a time, with the photo
   right on the listing (no need to open each profile). The script follows
   the "Next >" links until the last page.
3. Page 1 of each department starts with the Dean and Associate Dean of the
   whole faculty (the same two people repeat on every department of that
   faculty). Those are saved ONCE into a separate folder instead of being
   copied into every department folder.
4. Each department also has an "Adjunct Faculty" page; those people are
   included too (can be switched off below).
5. Some teachers have no personal photo and the site shows a generic
   placeholder (pic.jpg). You can choose to skip those.

Output
------
    <OUTPUT_DIR>/<Department_Name>/<Teacher_Name>.jpg
    <OUTPUT_DIR>/_Deans_and_Associate_Deans/<Name>.jpg
    <OUTPUT_DIR>/scrape_log.csv     (one row per person, with status)

Requirements
------------
    pip install requests beautifulsoup4
"""

import os
import re
import csv
import time
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ============================== CONFIGURATION ============================== #
# 1. Where everything gets saved (relative to this script, or an absolute
#    path such as r"C:\Users\YourName\Desktop\DIU_Faculty").
OUTPUT_DIR = r"C:\Users\Hp\Downloads\DIU Faculty Photos"                       # <-- CHANGE THIS if needed

# 2. Faculty portal homepage (only change if DIU moves the site).
HOME_URL = "https://faculty.daffodilvarsity.edu.bd/"

# 3. Parallel image downloads. Keep modest (3-6) to be polite to the server.
MAX_WORKERS = 5

# 4. Pause (seconds) between listing-page requests and before each download.
REQUEST_DELAY = 0.4

# 5. Timeout (seconds) for every HTTP request.
TIMEOUT = 20

# 6. Also save the Dean / Associate Dean of each faculty (once each)?
INCLUDE_DEANS = True

# 7. Also save people from each department's "Adjunct Faculty" page?
INCLUDE_ADJUNCT = True

# 8. Skip people who only have the generic placeholder photo (pic.jpg)?
SKIP_PLACEHOLDER_IMAGES = False

# 9. Folder name used for the Deans / Associate Deans.
DEANS_FOLDER = "_Deans_and_Associate_Deans"
# ============================================================================ #

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": HOME_URL,
}

session = requests.Session()
session.headers.update(HEADERS)

PLACEHOLDER_FILENAMES = {"pic.jpg"}

path_lock = threading.Lock()
used_paths = set()


# ------------------------------- helpers ---------------------------------- #
def sanitize_filename(name: str) -> str:
    """Turn a person/department name into a safe file or folder name."""
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w\s.-]", "", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name.replace(" ", "_") or "unnamed"


def fetch(url: str, retries: int = 3) -> requests.Response:
    """GET with a few retries for temporary failures."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            if resp.status_code in (403, 429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * attempt)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def get_soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch(url).text, "html.parser")


def unique_path(folder: str, base: str, ext: str, tag: str) -> str:
    """Never overwrite: if two people end up with the same file name in one
    folder, the second gets a suffix taken from their profile URL."""
    with path_lock:
        path = os.path.join(folder, f"{base}{ext}")
        if path in used_paths:
            path = os.path.join(folder, f"{base}_{tag}{ext}")
            n = 2
            while path in used_paths:
                path = os.path.join(folder, f"{base}_{tag}{n}{ext}")
                n += 1
        used_paths.add(path)
        return path


# ------------------------------- parsing ---------------------------------- #
def parse_departments(home_soup: BeautifulSoup):
    """Read the homepage: every 'Department of ...' link, with its faculty."""
    departments, seen = [], set()

    for a in home_soup.find_all("a", href=re.compile(r"/teachers/[^/?#]+$")):
        url = urljoin(HOME_URL, a["href"])
        text = a.get_text(" ", strip=True)
        if not text or url in seen:
            continue
        seen.add(url)

        fac_node = a.find_previous(string=re.compile(r"^\s*Faculty of"))
        faculty = fac_node.strip() if fac_node else "Unknown Faculty"

        departments.append({"faculty": faculty, "department": text, "url": url})

    return departments


def parse_cards(soup: BeautifulSoup, page_url: str):
    """
    Return every person shown on a listing page:
    [{"name", "designation", "profile_url", "image_url", "is_dean"}, ...]

    Cards are found via their photo (<img> under /images/). Anything shown
    BEFORE the 'Department of ...' heading is a faculty-level Dean/Associate
    Dean, everything after it belongs to the department.
    """
    body = soup.body or soup

    marker = None
    for h in body.find_all(re.compile(r"^h[1-6]$")):
        if re.match(r"^Department of", h.get_text(" ", strip=True)):
            marker = h
            break
    after_ids = {id(i) for i in marker.find_all_next("img")} if marker else None

    people = []
    for img in body.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if "/images/" not in src or "/dist/" in src:
            continue  # logos, icons, etc.

        card = img.find_parent("li") or img.parent
        link = card.find("a", href=re.compile(r"/profile/")) if card else None
        heading = card.find(re.compile(r"^h[1-6]$")) if card else None
        h4 = card.find("h4") if card else None

        if link and link.get_text(strip=True):
            name = link.get_text(" ", strip=True)
        elif heading:
            name = heading.get_text(" ", strip=True)
        else:
            name = (img.get("alt") or "").strip()
        if not name:
            continue

        designation = h4.get_text(" ", strip=True) if h4 else ""
        is_dean = after_ids is not None and id(img) not in after_ids

        people.append({
            "name": name,
            "designation": designation,
            "profile_url": urljoin(page_url, link["href"]) if link else "",
            "image_url": urljoin(page_url, src),
            "is_dean": is_dean,
        })

    return people


def find_next_page(soup: BeautifulSoup, current_url: str):
    a = soup.find("a", string=re.compile(r"Next"))
    if not a or not a.get("href") or a["href"].startswith("#"):
        return None
    nxt = urljoin(current_url, a["href"])
    return None if nxt == current_url else nxt


def find_adjunct_link(soup: BeautifulSoup, current_url: str):
    a = soup.find("a", string=re.compile(r"Adjunct Faculty", re.I))
    if a and a.get("href") and not a["href"].startswith("#"):
        return urljoin(current_url, a["href"])
    return None


def collect_department(dept: dict):
    """Walk all pages of one department (+ its adjunct page)."""
    members = []
    url, visited = dept["url"], set()
    adjunct_url = None

    while url and url not in visited and len(visited) < 60:
        visited.add(url)
        soup = get_soup(url)
        for p in parse_cards(soup, url):
            p["category"] = "faculty"
            members.append(p)
        if adjunct_url is None:
            adjunct_url = find_adjunct_link(soup, url)
        url = find_next_page(soup, url)
        time.sleep(REQUEST_DELAY)

    if INCLUDE_ADJUNCT and adjunct_url:
        try:
            soup = get_soup(adjunct_url)
            for p in parse_cards(soup, adjunct_url):
                p["category"] = "adjunct"
                p["is_dean"] = False
                members.append(p)
        except Exception as e:
            print(f"    ! Could not read adjunct page {adjunct_url}: {e}")

    return members


# ------------------------------ downloading ------------------------------- #
def download_image(img_url: str, dest_path: str) -> bool:
    try:
        resp = session.get(img_url, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ! Failed to download {img_url}: {e}")
        return False


def process_person(task: dict) -> dict:
    result = {**task, "image_path": "", "status": ""}
    img_url = task["image_url"]
    fname = os.path.basename(urlparse(img_url).path)

    if fname.lower() in PLACEHOLDER_FILENAMES:
        result["is_placeholder"] = True
        if SKIP_PLACEHOLDER_IMAGES:
            result["status"] = "skipped_placeholder"
            return result
    else:
        result["is_placeholder"] = False

    time.sleep(REQUEST_DELAY)

    ext = os.path.splitext(fname)[1].lower() or ".jpg"
    if len(ext) > 5:
        ext = ".jpg"

    folder = os.path.join(OUTPUT_DIR, task["folder"])
    os.makedirs(folder, exist_ok=True)

    slug = os.path.splitext(os.path.basename(urlparse(task["profile_url"]).path))[0] if task["profile_url"] else "dup"
    dest = unique_path(folder, sanitize_filename(task["name"]), ext, sanitize_filename(slug) or "dup")

    if download_image(img_url, dest):
        result["image_path"] = dest
        result["status"] = "placeholder_downloaded" if result["is_placeholder"] else "downloaded"
    else:
        result["status"] = "download_failed"
    return result


# --------------------------------- main ----------------------------------- #
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Reading department list from: {HOME_URL}")
    departments = parse_departments(get_soup(HOME_URL))
    if not departments:
        raise RuntimeError(
            "No departments found on the homepage. The site layout may have "
            "changed -- parse_departments() needs updating."
        )
    print(f"Found {len(departments)} departments.\n")

    tasks, seen_deans = [], set()

    for dept in departments:
        print(f"=== {dept['department']}  [{dept['faculty']}] ===")
        try:
            members = collect_department(dept)
        except Exception as e:
            print(f"  ! Skipping department, could not read it: {e}")
            continue

        dept_folder = sanitize_filename(dept["department"])
        seen_in_dept = set()
        n_faculty = n_deans = 0

        for p in members:
            key = (p["name"], p["image_url"])
            if p["is_dean"]:
                if not INCLUDE_DEANS:
                    continue
                dean_key = (p["profile_url"] or p["name"], p["image_url"])
                if dean_key in seen_deans:
                    continue
                seen_deans.add(dean_key)
                folder = DEANS_FOLDER
                n_deans += 1
            else:
                if key in seen_in_dept:
                    continue
                seen_in_dept.add(key)
                folder = dept_folder
                n_faculty += 1

            tasks.append({
                "faculty": dept["faculty"],
                "department": dept["department"],
                "folder": folder,
                "name": p["name"],
                "designation": p["designation"],
                "category": "dean" if p["is_dean"] else p["category"],
                "profile_url": p["profile_url"],
                "image_url": p["image_url"],
            })

        print(f"  {n_faculty} people found" + (f" (+{n_deans} new dean-level)" if n_deans else ""))

    total = len(tasks)
    print(f"\nDownloading {total} photos...\n")

    results, done = [], 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(process_person, t) for t in tasks]
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            done += 1
            ok = res["status"] in ("downloaded", "placeholder_downloaded")
            print(f"[{done}/{total}] [{'OK  ' if ok else '--  '}] {res['name']} "
                  f"({res['folder']}) -> {res['status']}")

    csv_path = os.path.join(OUTPUT_DIR, "scrape_log.csv")
    fields = ["faculty", "department", "folder", "name", "designation", "category",
              "profile_url", "image_url", "image_path", "status"]
    results.sort(key=lambda r: (r["faculty"], r["department"], r["name"]))
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})

    ok = sum(1 for r in results if r["status"] in ("downloaded", "placeholder_downloaded"))
    ph = sum(1 for r in results if r["status"] == "placeholder_downloaded")
    print(f"\nDone. {ok}/{total} photos downloaded ({ph} of them are the generic placeholder).")
    print(f"Log saved to: {csv_path}")
    print(f"Photos saved under: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
