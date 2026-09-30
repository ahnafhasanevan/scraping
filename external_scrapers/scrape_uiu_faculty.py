"""
UIU Faculty Member Scraper
==========================
Scrapes faculty names, designations, emails, and profile PHOTOS for every
department listed on:
    https://www.uiu.ac.bd/academics/faculty-members/

How it works
------------
1. The main faculty page shows one department at a time via JS tabs, but
   ALL department tables actually exist in the page's static HTML at once
   (they're just hidden with CSS until you click a tab). So we don't need
   Selenium/browser automation — plain requests + BeautifulSoup can see
   everything in one request.
2. For each department table, we grab every faculty member's name and their
   individual profile page link (e.g. https://cse.uiu.ac.bd/faculty/hsarwar).
3. We visit each profile page and locate their photo (WordPress content
   images living under /wp-content/uploads/, matched to the faculty name via
   the image's alt/title text — this reliably filters out logos, menu
   backgrounds, and social-media icons).
4. Photos are saved into one folder per department, named after each
   faculty member. A CSV log of everything (including failures) is also
   written so you can see what worked and what didn't.

Requirements
------------
    pip install requests beautifulsoup4
"""

import os
import re
import csv
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ============================== CONFIGURATION ============================== #
# 1. Where everything gets saved. Can be a relative path (created next to this
#    script) or a full absolute path, e.g. r"C:\Users\YourName\Desktop\UIU_Faculty"
OUTPUT_DIR = r"C:\Users\Hp\Downloads\ UIU Faculty Photos"                      # <-- CHANGE THIS if you want

# 2. The page to scrape (only change if UIU moves the page).
MAIN_URL = "https://www.uiu.ac.bd/academics/faculty-members/"

# 3. How many faculty profile pages to fetch at the same time.
#    Keep this modest (3-6) to be polite to the server and avoid getting
#    rate-limited / blocked.
MAX_WORKERS = 5

# 4. Small delay (in seconds) each worker waits before requesting a profile
#    page. Increase this if you get connection errors / timeouts.
REQUEST_DELAY = 0.5

# 5. Timeout (seconds) for each HTTP request.
TIMEOUT = 20

# 6. Some faculty have no personal photo uploaded, so UIU shows a generic
#    placeholder image instead. Set this to True to skip saving those.
SKIP_PLACEHOLDER_IMAGES = False
# ============================================================================ #

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)

# Filenames containing any of these are logos / icons / nav art, not photos.
NON_PROFILE_IMAGE_HINTS = [
    "logo", "cropped-", "favicon", "menu-background", "facebook",
    "twitter", "youtube", "instagram", "linkedin", "footer", "header-logo",
]

# Filenames containing any of these are UIU's generic "no photo" placeholder.
PLACEHOLDER_HINTS = [
    "default_image_uiu", "default-image", "avatar-default", "no-image", "no_image",
]


def sanitize_filename(name: str) -> str:
    """Turn a faculty/department name into a safe file or folder name."""
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w\s.-]", "", name)   # drop anything not alnum/space/dot/dash
    name = re.sub(r"\s+", " ", name).strip()
    return name.replace(" ", "_")


def get_soup(url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_departments(main_soup: BeautifulSoup):
    """
    Returns a list of:
        {"department": "Department of Computer Science and Engineering",
         "faculty": [{"name":.., "profile_url":.., "designation":.., "email":..}, ...]}
    """
    departments = []

    # Each department section is introduced by a heading like:
    # "Faculty Member List: Department of CSE"
    headings = main_soup.find_all(
        lambda tag: tag.name in ("h1", "h2", "h3", "h4", "h5")
        and tag.get_text(strip=True).lower().startswith("faculty member list")
    )

    if not headings:
        raise RuntimeError(
            "Could not find any 'Faculty Member List' headings on the page. "
            "The website's HTML structure may have changed since this script "
            "was written — you may need to update parse_departments()."
        )

    for heading in headings:
        heading_text = heading.get_text(strip=True)
        dept_name = heading_text.split(":", 1)[-1].strip() if ":" in heading_text else heading_text

        table = heading.find_next("table")
        if table is None:
            print(f"  ! No table found for department: {dept_name} (skipping)")
            continue

        faculty_list = []
        for row in table.find_all("tr"):
            if row.find("th"):
                continue  # header row

            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            name_cell = cells[1]  # columns are: SL, Name, Designation, PABX, Email
            link_tag = name_cell.find("a")

            if link_tag and link_tag.get("href"):
                name = link_tag.get_text(strip=True)
                profile_url = urljoin(MAIN_URL, link_tag["href"])
            else:
                name = name_cell.get_text(strip=True)
                profile_url = None

            if not name:
                continue

            designation = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            email = cells[4].get_text(strip=True) if len(cells) > 4 else ""

            faculty_list.append({
                "name": name,
                "profile_url": profile_url,
                "designation": designation,
                "email": email,
            })

        departments.append({"department": dept_name, "faculty": faculty_list})
        print(f"  Found {len(faculty_list)} faculty under: {dept_name}")

    return departments


def find_profile_image_url(profile_soup: BeautifulSoup, faculty_name: str, page_url: str):
    """Locate the faculty member's photo URL on their profile page."""
    name_lower = faculty_name.lower()
    name_words = set(re.sub(r"[.,]", " ", name_lower).split())

    candidates = []
    for img in profile_soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src or "/wp-content/uploads/" not in src:
            continue

        fname = src.rsplit("/", 1)[-1].lower()
        if any(hint in fname for hint in NON_PROFILE_IMAGE_HINTS):
            continue

        alt = (img.get("alt") or "").strip().lower()
        title = (img.get("title") or "").strip().lower()
        text = f"{alt} {title}".strip()

        if text and (text in name_lower or name_lower in text):
            score = 100
        else:
            text_words = set(re.sub(r"[.,]", " ", text).split())
            score = len(name_words & text_words)

        candidates.append((score, urljoin(page_url, src)))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def download_image(img_url: str, dest_path: str) -> bool:
    try:
        resp = session.get(img_url, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ! Failed to download image {img_url}: {e}")
        return False


def process_faculty(dept_folder: str, faculty: dict) -> dict:
    name = faculty["name"]
    profile_url = faculty["profile_url"]
    result = {**faculty, "department_folder": dept_folder,
              "image_url": "", "image_path": "", "status": ""}

    if not profile_url:
        result["status"] = "no_profile_link"
        return result

    time.sleep(REQUEST_DELAY)

    try:
        profile_soup = get_soup(profile_url)
    except Exception as e:
        result["status"] = f"profile_fetch_failed: {e}"
        return result

    img_url = find_profile_image_url(profile_soup, name, profile_url)
    if not img_url:
        result["status"] = "no_image_found"
        return result

    fname_lower = img_url.rsplit("/", 1)[-1].lower()
    is_placeholder = any(hint in fname_lower for hint in PLACEHOLDER_HINTS)
    if is_placeholder and SKIP_PLACEHOLDER_IMAGES:
        result["status"] = "skipped_placeholder"
        result["image_url"] = img_url
        return result

    ext = os.path.splitext(urlparse(img_url).path)[1] or ".jpg"
    if len(ext) > 5:  # sanity check, in case of a weird/long "extension"
        ext = ".jpg"

    safe_name = sanitize_filename(name)
    dest_dir = os.path.join(OUTPUT_DIR, dept_folder)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{safe_name}{ext}")

    ok = download_image(img_url, dest_path)
    result["image_url"] = img_url
    if ok:
        result["image_path"] = dest_path
        result["status"] = "placeholder_downloaded" if is_placeholder else "downloaded"
    else:
        result["status"] = "download_failed"

    return result


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Fetching main faculty page: {MAIN_URL}")
    main_soup = get_soup(MAIN_URL)

    departments = parse_departments(main_soup)
    all_results = []

    for dept in departments:
        dept_name = dept["department"]
        dept_folder = sanitize_filename(dept_name)
        faculty_members = dept["faculty"]
        print(f"\n=== {dept_name} ({len(faculty_members)} faculty) ===")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_faculty, dept_folder, fac): fac
                for fac in faculty_members
            }
            for future in as_completed(futures):
                res = future.result()
                all_results.append(res)
                ok_statuses = ("downloaded", "placeholder_downloaded")
                icon = "OK  " if res["status"] in ok_statuses else "FAIL"
                print(f"  [{icon}] {res['name']} -> {res['status']}")

    # Write a CSV summary/log of everything
    csv_path = os.path.join(OUTPUT_DIR, "scrape_log.csv")
    fieldnames = ["department_folder", "name", "designation", "email",
                  "profile_url", "image_url", "image_path", "status"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    total = len(all_results)
    ok = sum(1 for r in all_results if r["status"] in ("downloaded", "placeholder_downloaded"))
    print(f"\nDone. {ok}/{total} photos downloaded.")
    print(f"Log saved to: {csv_path}")
    print(f"Photos saved under: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
