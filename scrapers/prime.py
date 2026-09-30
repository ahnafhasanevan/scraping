"""Prime University (moved from primeuniversity.edu.bd to primeuniversity.ac.bd).
List page:    https://primeuniversity.ac.bd/department/department-of-english/faculty
Profile page: https://primeuniversity.ac.bd/faculty-profile.php?id=96
With --deep, profile ids are also enumerated to catch anyone missing from the lists.
"""
from .base_scraper import BaseScraper

BASE = "https://primeuniversity.ac.bd"

DEPARTMENTS = {
    "department-of-english": "English",
    "department-of-electrical-and-electronic-engineering-eee": "Electrical and Electronic Engineering",
    "department-of-computer-science-engineering": "Computer Science and Engineering",
    # Not verified - tried in case they exist (the department index is crawled as well):
    "department-of-civil-engineering": "Civil Engineering",
    "department-of-civil-engineering-ce": "Civil Engineering",
    "department-of-law": "Law",
    "department-of-business-administration": "Business Administration",
    "department-of-education": "Education",
    "department-of-bangla": "Bangla",
    "department-of-electronics-and-telecommunication-engineering-ete": "Electronics and Telecommunication Engineering",
    "department-of-fashion-design-and-apparel-engineering": "Fashion Design and Apparel Engineering",
}


class PrimeScraper(BaseScraper):
    key = "prime"
    short_name = "PU"
    name = "Prime University"
    homepage = BASE
    allowed_domains = ("primeuniversity.ac.bd", "primeuniversity.edu.bd")
    start_urls = (f"{BASE}/", f"{BASE}/department")
    seed_listing_urls = tuple(f"{BASE}/department/{slug}/faculty" for slug in DEPARTMENTS)
    fallback_start_urls = ("https://www.primeuniversity.edu.bd/department", "https://www.primeuniversity.edu.bd/")
    listing_patterns = (
        r"primeuniversity\.(?:ac|edu)\.bd/(?:index\.php/)?department/[\w-]+/faculty/?$",
        r"primeuniversity\.(?:ac|edu)\.bd/(?:index\.php/)?department/faculty_member/\d+/?$",
    )
    follow_patterns = (r"primeuniversity\.(?:ac|edu)\.bd/(?:index\.php/)?department/(?:details/\d+|[\w-]+)/?$",)
    profile_patterns = (r"faculty-profile\.php\?id=\d+", r"/faculty_member/details/\d+/\d+")
    exclude_patterns = (r"/file/", r"/admin/uploads/.*\.pdf")
    department_names = DEPARTMENTS
    id_profile_template = BASE + "/faculty-profile.php?id={id}"
    id_range = (1, 400)
