"""
AIUB Faculty Scraper
Scrapes all faculty from https://www.aiub.edu/faculty-list
Downloads profile photos organized by Faculty / Department
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
from urllib.parse import urljoin

# ============================================================
# CONFIGURATION - CHANGE THESE IF NEEDED
# ============================================================

# Main folder where everything will be saved
OUTPUT_DIR = Path(r"C:\Users\Hp\Downloads\Faculty Photo and Codes\AIUB Faculty Photos")          # <-- change this path if you want

# Sub-folders (created automatically)
IMAGES_DIR = OUTPUT_DIR / "images"              # photos: images/Faculty/Department/Name.jpg
CSV_FILE   = OUTPUT_DIR / "faculty_list.csv"
JSON_FILE  = OUTPUT_DIR / "faculty_list.json"

# Delay between image downloads (be polite)
DOWNLOAD_DELAY = 0.25   # seconds

# ============================================================
# END OF CONFIGURATION
# ============================================================

JSON_URL = "https://www.aiub.edu/Files/Uploads/public-employee-profiles/employeeProfiles.json"
BASE_URL = "https://www.aiub.edu"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def sanitize_filename(name: str) -> str:
    """Make a string safe for folder / file names."""
    if not name:
        return "Unknown"
    name = re.sub(r'[<>:"/\\|?*]', '', str(name))
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120]


def fetch_all_faculty() -> list[dict]:
    """Download the official employeeProfiles.json and return the list."""
    print("Fetching faculty data from AIUB...")
    try:
        resp = requests.get(JSON_URL, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Failed to fetch JSON: {e}")
        return []

    faculty_list = data.get("EmployeeProfileLightList", [])
    print(f"Total faculty members found: {len(faculty_list)}")
    return faculty_list


def download_image(url: str, save_path: Path) -> bool:
    """Download one image. Returns True on success."""
    if not url:
        return False
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, stream=True)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  Failed: {url} -> {e}")
        return False


def main():
    # Create folders
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Get all faculty data
    faculty_list = fetch_all_faculty()
    if not faculty_list:
        print("No data received. Exiting.")
        return

    records = []
    print("\nDownloading photos and organizing data...")

    for person in tqdm(faculty_list, desc="Processing"):
        # Basic info
        cv = person.get("CvPersonal") or {}
        other = person.get("PersonalOtherInfo") or {}

        name        = cv.get("Name") or "Unknown"
        email       = cv.get("Email") or ""
        user_id     = cv.get("UserId") or other.get("UserId") or ""
        faculty     = person.get("Faculty") or "Unknown Faculty"
        department  = person.get("HrDepartment") or "Unknown Department"
        position    = person.get("Position") or ""
        designation = person.get("Designation") or ""
        room        = other.get("RoomNo") or ""
        building    = other.get("BuildingNo") or ""
        research    = other.get("ResearchInterests") or ""
        academic    = other.get("AcademicInterests") or ""

        # Image URL
        photo_rel = other.get("SecondProfilePhoto") or ""
        if photo_rel:
            image_url = urljoin(BASE_URL, photo_rel)
        elif user_id:
            image_url = f"{BASE_URL}/Files/Uploads/public-employee-profiles/profile-pictures/{user_id}.jpg"
        else:
            image_url = ""

        # Safe folder structure: images / Faculty / Department /
        fac_folder  = sanitize_filename(faculty)
        dept_folder = sanitize_filename(department)
        person_dir  = IMAGES_DIR / fac_folder / dept_folder
        person_dir.mkdir(parents=True, exist_ok=True)

        # File name
        safe_name = sanitize_filename(name)
        image_filename = f"{safe_name}.jpg"
        image_path = person_dir / image_filename

        # Download (skip if already exists)
        downloaded = False
        if image_url and not image_path.exists():
            downloaded = download_image(image_url, image_path)
            time.sleep(DOWNLOAD_DELAY)
        elif image_path.exists():
            downloaded = True

        relative_image = str(image_path.relative_to(OUTPUT_DIR)) if downloaded else ""

        records.append({
            "name": name,
            "position": position,
            "designation": designation,
            "faculty": faculty,
            "department": department,
            "email": email,
            "room": room,
            "building": building,
            "research_interests": research,
            "academic_interests": academic,
            "user_id": user_id,
            "image_url": image_url,
            "local_image_path": relative_image,
            "profile_url": f"https://www.aiub.edu/faculty-list/faculty-profile?q={email}" if email else "",
        })

    # 3. Save CSV + JSON
    df = pd.DataFrame(records)
    df = df.sort_values(["faculty", "department", "name"]).reset_index(drop=True)

    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n" + "=" * 65)
    print("DONE!")
    print(f"Total faculty scraped : {len(df)}")
    print(f"Data saved to         : {OUTPUT_DIR.resolve()}")
    print(f"  • CSV               : {CSV_FILE.name}")
    print(f"  • JSON              : {JSON_FILE.name}")
    print(f"  • Photos            : {IMAGES_DIR.name}/<Faculty>/<Department>/<Name>.jpg")
    print("=" * 65)

    print("\nFaculty count by Faculty:")
    print(df["faculty"].value_counts().to_string())
    print("\nTop departments:")
    print(df["department"].value_counts().head(15).to_string())


if __name__ == "__main__":
    main()