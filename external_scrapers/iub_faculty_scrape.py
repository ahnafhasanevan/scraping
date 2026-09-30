"""
IUB Faculty Scraper
Scrapes all faculty members from https://iub.ac.bd/faculties
Downloads profile photos organized by department
Saves CSV + JSON metadata
"""

import os
import re
import time
import json
import requests
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from urllib.parse import urlparse, unquote

# ============================================================
# CONFIGURATION - CHANGE THESE IF NEEDED
# ============================================================

# Folder where everything will be saved (relative to this script)
OUTPUT_DIR = Path(r"C:\Users\Hp\Downloads\IUB Faculty Photos")          # <-- change this if you want a different location

# Sub-folders that will be created automatically
IMAGES_DIR = OUTPUT_DIR / "images"             # photos go here: images/Department_Name/Name.jpg
CSV_FILE   = OUTPUT_DIR / "faculty_list.csv"
JSON_FILE  = OUTPUT_DIR / "faculty_list.json"

# How many faculty members to fetch per API request
PAGE_SIZE = 100

# Small delay between image downloads (be polite to the server)
DOWNLOAD_DELAY = 0.3   # seconds

# ============================================================
# END OF CONFIGURATION
# ============================================================

BASE_API = "https://iub.ac.bd/api/faculties-academic-staffs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def sanitize_filename(name: str) -> str:
    """Make a string safe to use as a folder / file name."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)          # remove illegal characters
    name = re.sub(r'\s+', ' ', name).strip()          # collapse whitespace
    return name[:120]                                 # keep it reasonably short

def get_extension_from_url(url: str) -> str:
    """Extract file extension from image URL."""
    path = urlparse(url).path
    ext = Path(unquote(path)).suffix.lower()
    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        return ext
    return '.jpg'   # fallback

def fetch_all_faculty() -> list[dict]:
    """Fetch every faculty member using the official API (with pagination)."""
    all_faculty = []
    page = 1

    print("Fetching faculty data from IUB API...")
    while True:
        params = {
            "school": "",
            "department": "",
            "page": page,
            "size": PAGE_SIZE,
            "draft": "true",
        }
        try:
            resp = requests.get(BASE_API, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break

        faculties = data.get("faculties", [])
        if not faculties:
            break

        all_faculty.extend(faculties)
        total = data.get("pagination", {}).get("facultyTotal", 0)
        print(f"  Page {page}: got {len(faculties)} faculty (total so far: {len(all_faculty)} / {total})")

        if len(all_faculty) >= total:
            break
        page += 1
        time.sleep(0.5)   # be gentle

    print(f"\nTotal faculty members fetched: {len(all_faculty)}")
    return all_faculty

def download_image(url: str, save_path: Path) -> bool:
    """Download a single image. Returns True on success."""
    if not url or not url.startswith("http"):
        return False
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  Failed to download {url}: {e}")
        return False

def main():
    # Create output directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch all faculty
    faculty_list = fetch_all_faculty()
    if not faculty_list:
        print("No faculty data received. Exiting.")
        return

    # 2. Process each faculty member
    records = []
    print("\nDownloading profile photos and organizing data...")

    for person in tqdm(faculty_list, desc="Processing"):
        name       = person.get("name") or "Unknown"
        department = person.get("department") or "Unknown_Department"
        school     = person.get("school") or ""
        position   = person.get("position") or ""
        email      = person.get("email") or ""
        education  = person.get("education") or ""
        office     = person.get("officePhone") or ""
        slug       = person.get("slug") or ""
        image_url  = person.get("image") or ""

        # Safe folder & file names
        dept_folder = sanitize_filename(department)
        person_folder = IMAGES_DIR / dept_folder
        person_folder.mkdir(parents=True, exist_ok=True)

        # Image filename
        safe_name = sanitize_filename(name)
        ext = get_extension_from_url(image_url)
        image_filename = f"{safe_name}{ext}"
        image_path = person_folder / image_filename

        # Download image (skip if already exists)
        downloaded = False
        if image_url and not image_path.exists():
            downloaded = download_image(image_url, image_path)
            time.sleep(DOWNLOAD_DELAY)
        elif image_path.exists():
            downloaded = True

        # Relative path for the CSV (easy to open later)
        relative_image = str(image_path.relative_to(OUTPUT_DIR)) if downloaded else ""

        records.append({
            "name": name,
            "position": position,
            "department": department,
            "school": school,
            "email": email,
            "education": education,
            "office_phone": office,
            "slug": slug,
            "profile_url": f"https://iub.ac.bd/faculties/{slug}" if slug else "",
            "image_url": image_url,
            "local_image_path": relative_image,
            "linkedin": person.get("linkedInLink") or "",
            "google_scholar": person.get("googleScholarLink") or "",
            "orcid": person.get("orchidLink") or "",
        })

    # 3. Save CSV and JSON
    df = pd.DataFrame(records)
    df = df.sort_values(["department", "name"]).reset_index(drop=True)

    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n" + "="*60)
    print("DONE!")
    print(f"Total faculty scraped : {len(df)}")
    print(f"Data saved to         : {OUTPUT_DIR.resolve()}")
    print(f"  - CSV               : {CSV_FILE.name}")
    print(f"  - JSON              : {JSON_FILE.name}")
    print(f"  - Photos            : {IMAGES_DIR.name}/<Department>/<Name>.jpg")
    print("="*60)

    # Quick department count
    print("\nFaculty count per department:")
    print(df["department"].value_counts().to_string())

if __name__ == "__main__":
    main()