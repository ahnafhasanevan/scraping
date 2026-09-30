"""Southeast University.
List page: https://seu.edu.bd/cse-faculties-staff   (one per department: <dept>-faculties-staff)
Older pages: https://seu.edu.bd/dept/islamic_studies.php?id=faculty
"""
from .base_scraper import BaseScraper

BASE = "https://seu.edu.bd"

DEPARTMENTS = {
    "cse": "Computer Science and Engineering",
    "eee": "Electrical and Electronic Engineering",
    "textile": "Textile Engineering",
    "pharmacy": "Pharmacy",
    "architecture": "Architecture",
    "bba": "Business Administration",
    "mba": "Business Administration",
    "economics": "Economics",
    "english": "English",
    "law": "Law",
    "bangla": "Bangla",
    "islamic-studies": "Islamic Studies",
    "islamic_studies": "Islamic Studies",
    "ict": "Information and Communication Technology",
    "ice": "Information and Communication Engineering",
    "ete": "Information and Communication Engineering",
    "ged": "General Education",
    "math": "Mathematics",
}
# Verified: cse, english, law, textile, pharmacy. The rest follow the same pattern and are
# tried as well (a missing page is simply skipped).
_SLUGS = ("cse", "english", "law", "textile", "pharmacy", "eee", "bba", "economics", "architecture",
          "bangla", "islamic-studies", "ict", "ice", "ete", "mba", "math", "ged")


class SEUScraper(BaseScraper):
    key = "seu"
    short_name = "SEU"
    name = "Southeast University"
    homepage = BASE
    allowed_domains = ("seu.edu.bd",)
    start_urls = (f"{BASE}/",)
    seed_listing_urls = tuple(f"{BASE}/{slug}-faculties-staff" for slug in _SLUGS) + (
        f"{BASE}/dept/islamic_studies.php?id=faculty",
    )
    listing_patterns = (r"seu\.edu\.bd/[\w-]+-faculties-staff/?$", r"seu\.edu\.bd/dept/\w+\.php\?id=faculty$")
    follow_patterns = (
        r"seu\.edu\.bd/(?:bsc|ba|bba|llb|bpharm|b-pharm|bss|ma|mba|msc|llm|mpharm|barch)[-_]in[-_][\w-]+/?$",
        r"seu\.edu\.bd/dept/\w+\.php$",
        r"seu\.edu\.bd/(?:school|department)s?[-_/][\w-]*$",
    )
    profile_patterns = (r"seu\.edu\.bd/(?:faculty|profile|faculty-profile)/[\w.-]+/?$",)
    exclude_patterns = (r"id=research", r"id=chairman_message", r"/notice", r"/news")
    department_names = DEPARTMENTS
