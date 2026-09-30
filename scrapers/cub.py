"""Canadian University of Bangladesh.
Central directory: http://home.cub.edu.bd/cub/faculty.php?TA=FacultyReg
Department sites:  https://cse.cub.edu.bd/cse/faculty.php (same layout on eee., law., ...)
Profile page:      https://www.cub.edu.bd/faculty_member_details.php?faculty=dr-kazi-abu-taher
"""
from .base_scraper import BaseScraper

DEPARTMENTS = {
    "cse": "Computer Science and Engineering",
    "eee": "Electrical and Electronic Engineering",
    "business": "Business Administration",
    "bba": "Business Administration",
    "law": "Law",
    "english": "English",
    "ged": "General Education",
    "pbh": "Public Health",
    "mcj": "Media, Communication and Journalism",
}
_SUBSITES = ("cse", "eee", "business", "law", "english", "ged", "pbh", "mcj")


class CUBScraper(BaseScraper):
    key = "cub"
    short_name = "CUB"
    name = "Canadian University of Bangladesh"
    homepage = "https://cub.edu.bd"
    allowed_domains = ("cub.edu.bd",)
    start_urls = ("https://cub.edu.bd/",) + tuple(f"https://{s}.cub.edu.bd/" for s in _SUBSITES)
    seed_listing_urls = (
        "http://home.cub.edu.bd/cub/faculty.php?TA=FacultyReg",
        "http://home.cub.edu.bd/cub/faculty.php",
    ) + tuple(f"https://{s}.cub.edu.bd/{s}/faculty.php" for s in _SUBSITES)
    listing_patterns = (
        r"cub\.edu\.bd/[\w-]+/faculty\.php(?:\?.*)?$",
        r"cub\.edu\.bd/faculty(?:_members?|_list)?\.php(?:\?.*)?$",
    )
    follow_patterns = (r"^https?://(?:cse|eee|business|law|english|ged|pbh|mcj)\.cub\.edu\.bd/?(?:[\w-]+/?)?$",)
    profile_patterns = (
        r"faculty_member_details\.php\?faculty=",
        r"faculty_details\.php\?",
        r"cub\.edu\.bd/[\w-]+/faculty_details?/[\w-]+",
    )
    exclude_patterns = (r"admission\.php", r"/notice", r"/news")
    department_names = DEPARTMENTS
