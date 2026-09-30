"""Stand-alone university scripts, run from main.py without changing them.

Each script in this folder is kept exactly as it was written. To connect it:
  1. the script is loaded as a module (its own settings and logic stay intact),
  2. only its output-folder setting is pointed at <output>/photos/<University> so all
     universities end up side by side (set EXTERNAL_SCRIPTS_OWN_OUTPUT = True in
     config.py to keep each script's own folder instead),
  3. its main() is called,
  4. the CSV the script writes is read back so its people appear in the run summary
     and in data/processed/all_faculty_merged.*
"""
from __future__ import annotations

import csv
import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from utils.cleaner import clean_text, safe_filename
from utils.models import FacultyRecord

log = logging.getLogger("scraper.external")
HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ExternalScript:
    key: str
    short_name: str
    name: str
    homepage: str
    script: str       # file name in this folder
    csv_name: str     # the CSV the script writes into its output folder

    @property
    def folder_name(self) -> str:
        return safe_filename(f"{self.short_name} - {self.name}", 60)


EXTERNAL_SCRIPTS = {
    s.key: s
    for s in (
        ExternalScript("diu", "DIU", "Daffodil International University",
                       "https://faculty.daffodilvarsity.edu.bd", "scrape_diu_faculty.py", "scrape_log.csv"),
        ExternalScript("uiu", "UIU", "United International University",
                       "https://www.uiu.ac.bd", "scrape_uiu_faculty.py", "scrape_log.csv"),
        ExternalScript("aiub", "AIUB", "American International University-Bangladesh",
                       "https://www.aiub.edu", "aiub_faculty_scrape.py", "faculty_list.csv"),
        ExternalScript("iub", "IUB", "Independent University Bangladesh",
                       "https://iub.ac.bd", "iub_faculty_scrape.py", "faculty_list.csv"),
        ExternalScript("nsu", "NSU", "North South University",
                       "https://www.northsouth.edu", "nsu_faculty_photos.py", "faculty_photos_index.csv"),
    )
}


def load_script(script: ExternalScript):
    """Import the script file as a fresh module (its settings are read at import)."""
    path = HERE / script.script
    spec = importlib.util.spec_from_file_location(f"external_{script.key}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def script_output_dir(module) -> Path:
    for var in ("OUTPUT_DIR", "SAVE_DIR"):
        if hasattr(module, var):
            return Path(os.path.abspath(os.path.expanduser(str(getattr(module, var)))))
    raise AttributeError("script has no OUTPUT_DIR / SAVE_DIR setting")


def redirect_output(module, new_dir: Path) -> None:
    """Point the script's output setting (and paths derived from it) at new_dir."""
    for var in ("OUTPUT_DIR", "SAVE_DIR"):
        if not hasattr(module, var):
            continue
        old = getattr(module, var)
        old_base = Path(str(old))
        setattr(module, var, new_dir if isinstance(old, Path) else str(new_dir))
        # AIUB / IUB build IMAGES_DIR, CSV_FILE, JSON_FILE from OUTPUT_DIR when imported.
        for name in dir(module):
            value = getattr(module, name)
            if name != var and name.isupper() and isinstance(value, Path):
                try:
                    setattr(module, name, new_dir / value.relative_to(old_base))
                except ValueError:
                    pass


def run_external(script: ExternalScript, photos_dir: Path, output_dir: Path, own_output: bool = False) -> list[FacultyRecord]:
    """Run one stand-alone script and return its people as FacultyRecords."""
    log.info("%s: running %s (stand-alone script) ...", script.short_name, script.script)
    module = load_script(script)
    if own_output:
        target = script_output_dir(module)
    else:
        target = photos_dir / script.folder_name
        redirect_output(module, target)
    target.mkdir(parents=True, exist_ok=True)
    try:
        module.main()
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # SystemExit included: one script must not stop the others
        log.error("%s: %s stopped with an error: %s", script.short_name, script.script, exc)
    records = read_results(script, target, output_dir)
    log.info("%s: %d people, %d photos saved -> %s", script.short_name, len(records),
             sum(1 for r in records if r.photo_file), target)
    return records


def read_results(script: ExternalScript, target: Path, output_dir: Path) -> list[FacultyRecord]:
    """Map the script's own CSV (each script uses different columns) to FacultyRecords."""
    csv_path = target / script.csv_name
    if not csv_path.is_file():
        log.warning("%s: %s was not written - no summary for this university", script.short_name, csv_path)
        return []
    records = []
    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = clean_text(row.get("name"))
            if not name:
                continue
            department = clean_text(row.get("department") or row.get("department_folder") or "")
            if "_" in department and " " not in department:
                department = department.replace("_", " ")
            saved = row.get("image_path") or row.get("local_image_path") or row.get("saved_file") or ""
            photo_file = ""
            if saved:
                path = Path(saved) if os.path.isabs(saved) else target / saved
                if path.is_file():
                    try:
                        photo_file = str(path.relative_to(output_dir))
                    except ValueError:
                        photo_file = str(path)
            status = row.get("status") or ("downloaded" if photo_file else
                                           "download failed" if row.get("image_url") else "no photo found")
            records.append(FacultyRecord(
                university=script.short_name,
                university_name=script.name,
                department=department or "Other",
                name=name,
                designation=clean_text(row.get("designation") or row.get("position") or ""),
                email=clean_text(row.get("email") or ""),
                research_interests=clean_text(row.get("research_interests") or ""),
                profile_url=row["profile_url"] if (row.get("profile_url") or "").startswith("http") else "",
                photo_url=row.get("image_url") or "",
                source_page=script.homepage,
                photo_file=photo_file,
                photo_status=status,
            ))
    return records
