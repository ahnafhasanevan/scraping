"""Bangladesh University of Business and Technology.
List page:    https://www.bubt.edu.bd/department/department-of-computer-science-engineering/faculty
Profile page: https://bubt.edu.bd/department/department-of-computer-science-engineering/faculty/profile/SJC
Older lists:  https://www.bubt.edu.bd/home/faculty_member/english
"""
from .base_scraper import BaseScraper

BASE = "https://www.bubt.edu.bd"

DEPARTMENTS = {
    "department-of-computer-science-engineering": "Computer Science and Engineering",
    "department-of-electrical-electronic-engineering": "Electrical and Electronic Engineering",
    "department-of-management": "Management",
    "department-of-mathematics-statistics": "Mathematics and Statistics",
    "department-of-accounting": "Accounting",
    "department-of-finance": "Finance",
    "department-of-marketing": "Marketing",
    "department-of-textile-engineering": "Textile Engineering",
    "department-of-civil-engineering": "Civil Engineering",
    "department-of-english": "English",
    "department-of-economics": "Economics",
    "department-of-law-justice": "Law and Justice",
    "department-of-business-administration": "Business Administration",
    # short names used by the older pages and sub-domains
    "cse": "Computer Science and Engineering",
    "eee": "Electrical and Electronic Engineering",
    "management": "Management",
    "accounting": "Accounting",
    "finance": "Finance",
    "marketing": "Marketing",
    "textile": "Textile Engineering",
    "civil": "Civil Engineering",
    "english": "English",
    "economics": "Economics",
    "law": "Law and Justice",
}
_SLUGS = [k for k in DEPARTMENTS if k.startswith("department-of-")]


class BUBTScraper(BaseScraper):
    key = "bubt"
    short_name = "BUBT"
    name = "Bangladesh University of Business and Technology"
    homepage = BASE
    allowed_domains = ("bubt.edu.bd",)
    blocked_hosts = ("classic.bubt.edu.bd", "dev.bubt.edu.bd", "newera2026.bubt.edu.bd")
    start_urls = (f"{BASE}/", "https://bubt.edu.bd/home/view_all_departments")
    seed_listing_urls = tuple(f"{BASE}/department/{slug}/faculty" for slug in _SLUGS) + (
        "https://cse.bubt.edu.bd/faculty",
        f"{BASE}/home/faculty_member/english",
        f"{BASE}/home/faculty_member/economics",
    )
    listing_patterns = (
        r"bubt\.edu\.bd/department/[\w-]+/faculty/?$",
        r"bubt\.edu\.bd/home/faculty_member/[\w-]+/?$",
        r"^https?://cse\.bubt\.edu\.bd/faculty/?$",
    )
    follow_patterns = (
        r"bubt\.edu\.bd/department/(?:department-of-)?[\w-]+/?$",
        r"bubt\.edu\.bd/department/information/[\w-]+",
        r"bubt\.edu\.bd/faculty/faculty-of-[\w-]+",
        r"view_all_departments",
    )
    profile_patterns = (r"/faculty/profile/[\w.-]+/?$", r"/department/member_details/\d+")
    exclude_patterns = (r"/course_details/", r"/dept_menu_details/", r"/notice", r"/news")
    department_names = DEPARTMENTS
