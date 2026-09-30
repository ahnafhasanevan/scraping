# Bangladesh University Faculty Scraper

A Python project that collects publicly listed **faculty member photos and details** from the official websites of fourteen private universities in Bangladesh. Photos are saved one folder per university and department, and the details are saved as a clean dataset (CSV / JSON / Excel).

---

## Table of Contents

1. [Quick Start (Windows)](#quick-start-windows)
2. [Target Universities](#target-universities)
3. [Data Collected](#data-collected)
4. [Project Structure](#project-structure)
5. [Requirements](#requirements)
6. [Installation](#installation)
7. [Usage](#usage)
8. [Configuration](#configuration)
9. [Output Format](#output-format)
10. [How It Works](#how-it-works)
11. [Known Challenges & Troubleshooting](#known-challenges--troubleshooting)
12. [Responsible Scraping & Ethics](#responsible-scraping--ethics)
13. [Tests](#tests)
14. [Roadmap](#roadmap)
15. [License](#license)

---

## Quick Start (Windows)

1. Install **Python 3.9+** from <https://www.python.org/downloads/> and tick **"Add python.exe to PATH"**.
2. Put this project folder anywhere, for example inside `C:\Users\Hp\Downloads\Faculty Photo and Codes`.
3. Double-click **`run_windows.bat`**.

The first run creates a virtual environment and installs the requirements, then scrapes all fourteen universities. Photos and data go to:

```
C:\Users\Hp\Downloads\Faculty Photo and Codes
```

(Change `WINDOWS_OUTPUT_DIR` in `config.py`, or pass `--output "D:\Some\Folder"`. If the folder cannot be created, the scraper falls back to an `output` folder next to the code.)

---

## Target Universities

| #  | University                                     | Key     | Where the faculty lists are                                                      |
|----|------------------------------------------------|---------|----------------------------------------------------------------------------------|
| 1  | East West University                           | `ewu`   | `fse./fbe./flass.ewubd.edu/<department>/faculty-members`                         |
| 2  | Southeast University                           | `seu`   | `seu.edu.bd/<dept>-faculties-staff`                                              |
| 3  | University of Liberal Arts Bangladesh          | `ulab`  | `ulab.edu.bd/people/<dept>-faculty` (+ department sub-sites, paged)              |
| 4  | BGMEA University of Fashion & Technology       | `buft`  | `buft.edu.bd/<department>/teaching-staff`                                        |
| 5  | Canadian University of Bangladesh              | `cub`   | `home.cub.edu.bd/cub/faculty.php` and `<dept>.cub.edu.bd/<dept>/faculty.php`     |
| 6  | University of Asia Pacific                     | `uap`   | one sub-site per department (`cse.`, `ce.`, `eee.`, `pharmacy.`, `lhr.` ...)     |
| 7  | European University of Bangladesh              | `eub`   | `eub.edu.bd/department-of-<dept>/<id>/` (JavaScript site)                        |
| 8  | Bangladesh University of Business & Technology | `bubt`  | `bubt.edu.bd/department/<department>/faculty`                                    |
| 9  | Prime University                               | `prime` | `primeuniversity.ac.bd/department/<department>/faculty` (moved from `.edu.bd`)   |
| 10 | Daffodil International University            | `diu`   | stand-alone script `external_scrapers/scrape_diu_faculty.py`                     |
| 11 | United International University               | `uiu`   | stand-alone script `external_scrapers/scrape_uiu_faculty.py`                     |
| 12 | American International University-Bangladesh  | `aiub`  | stand-alone script `external_scrapers/aiub_faculty_scrape.py`                    |
| 13 | Independent University Bangladesh             | `iub`   | stand-alone script `external_scrapers/iub_faculty_scrape.py`                     |
| 14 | North South University                        | `nsu`   | stand-alone script `external_scrapers/nsu_faculty_photos.py`                     |

Universities 10–14 use proven, site-specific scripts that are kept **exactly as written**. `main.py` loads each one, points its output folder to `photos\<University>\` (set `EXTERNAL_SCRIPTS_OWN_OUTPUT = True` in `config.py` to use the folder written inside the script instead), runs its `main()`, and reads the CSV it produces into the combined dataset. Each script keeps its own folder layout, delays and CSV log. These scripts always download photos, even with `--no-images`.

The start points for universities 1–9 were taken from the live websites. The scraper does not depend on them alone: it also crawls each site's department pages to find list pages that are new or were renamed.

---

## Data Collected

For each faculty member (availability varies by university):

- University name and department
- Full name, designation (normalised, e.g. "Asst. Prof." → "Assistant Professor")
- Academic qualifications / degrees
- Email and phone (only if publicly displayed)
- Research interests
- Profile page URL, photo URL
- **Downloaded photo** and a status (`downloaded`, `no photo found`, `placeholder (no real photo)` ...)

Officers and lab staff that some "Faculty & Staff" pages include are skipped (use `--include-staff` to keep them). Missing fields are left empty.

---

## Project Structure

```
scraping/
├── README.md
├── requirements.txt          # runtime dependencies
├── requirements-dev.txt      # + pytest
├── run_windows.bat           # one-click setup + run on Windows
├── config.py                 # settings (output folder, delays, image rules ...)
├── main.py                   # command line entry point
├── scrapers/
│   ├── __init__.py           # registry of university scrapers
│   ├── base_scraper.py       # shared engine: discovery, pagination, profiles, departments
│   ├── ewu.py  seu.py  ulab.py  buft.py  cub.py
│   └── uap.py  eub.py  bubt.py  prime.py      # per-university start pages & URL rules
├── external_scrapers/
│   ├── __init__.py           # runs the stand-alone scripts below unchanged
│   ├── scrape_diu_faculty.py  scrape_uiu_faculty.py  aiub_faculty_scrape.py
│   └── iub_faculty_scrape.py  nsu_faculty_photos.py
├── utils/
│   ├── http_client.py        # retries, rate limit, robots.txt, TLS fallback, headless browser
│   ├── html_tools.py         # image URLs (lazy-load, srcset, CSS), links, pagination
│   ├── extractor.py          # finds faculty "cards", tables, embedded JSON, profile pages
│   ├── cleaner.py            # names, designations, emails, Windows-safe file names
│   ├── image_downloader.py   # download, validate, de-duplicate, save photos
│   ├── exporter.py           # CSV / JSON / Excel
│   └── models.py             # FacultyRecord
└── tests/                    # unit tests + an end-to-end test against a mock website
```

---

## Requirements

- Python 3.9+
- `requests`, `beautifulsoup4`, `lxml`, `pandas`, `openpyxl`, `tqdm`, `Pillow`
- `selenium` *(for JavaScript-rendered pages)*. Selenium 4 downloads the browser driver by itself, so `webdriver-manager` is no longer needed. It needs Google Chrome, Microsoft Edge (pre-installed on Windows 10/11) or Firefox.

---

## Installation

```bash
# 1. Get the code
git clone https://github.com/ahnafhasanevan/scraping.git
cd scraping

# 2. (Recommended) Create a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

On Windows, `run_windows.bat` does steps 2–3 for you.

---

## Usage

```bash
python main.py --all                          # every university: photos + CSV
python main.py --university ewu               # one university
python main.py --university seu buft cub      # several
python main.py --all --format xlsx            # Excel dataset (csv / json / xlsx / all)
python main.py --all --no-images              # dataset only, no photos
python main.py --list                         # show the university keys
```

Useful options:

| Option | Meaning |
|---|---|
| `--output PATH` | where to save everything (default: `C:\Users\Hp\Downloads\Faculty Photo and Codes` on Windows) |
| `--profiles always` | open every profile page and prefer its (usually larger) photo. Default `auto` opens a profile only when the list has no photo |
| `--render always` / `never` | force / disable the headless browser (default `auto`: only for pages that need JavaScript) |
| `--deep` | also check numbered profile pages (e.g. Prime University `faculty-profile.php?id=1..400`) to catch people missing from lists |
| `--jpg` | convert every photo to `.jpg` |
| `--include-staff` | keep officers/lab staff |
| `--delay 3` | slower, more polite crawling |
| `--verbose` | show every page visited |

Supported university keys: `ewu`, `seu`, `ulab`, `buft`, `cub`, `uap`, `eub`, `bubt`, `prime`, `diu`, `uiu`, `aiub`, `iub`, `nsu`

Re-running is safe: photos that are already on disk are not downloaded again.

---

## Configuration

Edit `config.py` to change the defaults:

```python
WINDOWS_OUTPUT_DIR = r"C:\Users\Hp\Downloads\Faculty Photo and Codes"
REQUEST_DELAY = 1.5          # seconds between page requests to the same site (be polite!)
TIMEOUT = 25                 # request timeout in seconds
MAX_RETRIES = 3              # retries with exponential back-off
DOWNLOAD_IMAGES = True       # photos are the main goal
USE_SELENIUM = "auto"        # True / False / "auto"
VISIT_PROFILES = "auto"      # "auto" / "always" / "never"
RESPECT_ROBOTS_TXT = True
PLACEHOLDER_REPEAT_THRESHOLD = 3   # same picture for 3+ people = "no photo" placeholder
```

---

## Output Format

```
C:\Users\Hp\Downloads\Faculty Photo and Codes\
├── photos\
│   ├── EWU - East West University\
│   │   ├── Computer Science and Engineering\
│   │   │   ├── Dr. Taskeed Jabid.jpg
│   │   │   └── ...
│   │   └── Pharmacy\ ...
│   ├── ULAB - University of Liberal Arts Bangladesh\ ...
│   └── ...
├── data\
│   ├── raw\ewu_faculty.csv, seu_faculty.csv, ...     # one file per university
│   ├── processed\all_faculty_merged.csv              # everything together
│   └── image_manifest.json                           # remembers downloads for re-runs
└── logs\scraper.log
```

**Sample row:**

| university | department | name | designation | email | profile_url | photo_url | photo_file | photo_status |
|---|---|---|---|---|---|---|---|---|
| EWU | Computer Science and Engineering | Dr. Example Name | Professor | example@ewubd.edu | https://.../faculty-view/example | https://.../example.jpg | photos\EWU - East West University\Computer Science and Engineering\Dr. Example Name.jpg | downloaded |

CSV files are written as UTF-8 with BOM so they open correctly in Excel.

---

## How It Works

Instead of one brittle CSS selector per website, a shared engine recognises what every faculty page has in common. Each university module only adds its start pages, URL rules and department names.

1. **Discover faculty lists.** Start from known list pages and the home/department pages, then follow links whose text or URL looks like a faculty list ("Faculty Members", "Teaching Staff", `/people/...-faculty` ...). Guessed URLs that 404, redirect elsewhere or show a "Page not found" page are ignored.
2. **Find faculty "cards" on any layout.** For every portrait image, the extractor climbs the HTML tree to the largest block that contains no other portrait. That block is one person's card, whether it is a grid card, a table row or loose headings and paragraphs. The name and designation are then picked from it. Logos, banners, sliders, news pictures, navigation and footers are filtered out.
3. **Handle modern sites.** Lazy-loaded images (`data-src`, `srcset`, CSS `background-image`), data embedded as JSON (Next.js `__NEXT_DATA__`, React Server Components, Laravel Inertia, JSON-LD), and, when needed, a headless browser that scrolls and presses "Load more".
4. **Walk pagination** (`?page=2`, `/page/2/`, "Next ›").
5. **Visit profile pages** when a list has no photo (or always, with `--profiles always`) and pick the portrait that best matches the person's name.
6. **Download photos** in parallel (rate limited per site). Thumbnails are upgraded to the original (`photo-150x150.jpg` → `photo.jpg`, Drupal image styles), files are checked to be real images of a reasonable size, and "no photo" placeholders are detected when the same picture is used for several people.
7. **Clean & save.** Names, designations and emails are normalised (including `name[at]uni[dot]edu`), duplicates are merged, and file names are made safe for Windows.

---

## Known Challenges & Troubleshooting

- **A university returns 0 people** – run it alone with details: `python main.py -u eub -v` and check `logs\scraper.log`. Sites get redesigned; add the new list page to `seed_listing_urls` in `scrapers/<key>.py`.
- **JavaScript sites (e.g. EUB)** need Chrome, Edge or Firefox. Edge is already installed on Windows, and Selenium downloads its driver automatically on first use.
- **TLS / certificate errors** – several university sites have misconfigured certificates. The scraper retries those hosts without verification and logs a warning (`ALLOW_INSECURE_SSL_FALLBACK` in `config.py`).
- **Slow or unreachable sites** – requests are retried with back-off, and a host that keeps failing is skipped so the run can continue.
- **Duplicate faculty** – people listed on several pages are merged (same name + same photo/profile).
- **Rate limiting / blocking** – keep `REQUEST_DELAY` reasonable. Pages returning 403/503 are retried in the headless browser.

---

## Responsible Scraping & Ethics

- Only **publicly available** information is collected, and `robots.txt` is respected by default.
- Requests are rate limited per website (`REQUEST_DELAY`) so university servers are not overloaded.
- Use the data only for legitimate academic, research, or educational purposes.
- **Do not** use collected emails or phone numbers for spam or unsolicited marketing.
- Faculty members' personal data should be handled respectfully; remove any entry on request.

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers the extraction heuristics on many page layouts, every university's URL rules, and an end-to-end run against a local mock university website. That run includes pagination, profile pages, a JavaScript page, placeholders, `robots.txt`, soft-404s and re-runs.

---

## Roadmap

- [x] Scrapers for EWU, SEU, ULAB, BUFT, CUB, UAP, EUB, BUBT and Prime University
- [x] DIU, UIU, AIUB, IUB and NSU stand-alone scripts connected to `main.py`
- [x] Merge and clean all datasets
- [x] Photo downloader (full-size upgrade, validation, placeholder detection, resumable)
- [x] JavaScript rendering fallback
- [ ] Add scheduled re-scraping to keep data fresh

---

## License

This project is released under the **MIT License** (TODO: change if needed).

The scraped data belongs to the respective universities and individuals; this project only provides tooling to collect publicly listed information.

---

## Author

**TODO: Your Name**
Email: your@email.com
GitHub: https://github.com/ahnafhasanevan
