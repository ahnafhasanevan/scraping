"""University of Asia Pacific - every department runs its own sub-site with its own layout:
https://cse.uap-bd.edu/people/faculty/        (profiles: /people/faculty/<initials>/)
https://ce.uap-bd.edu/faculty.html            (+ faculty_on_leave.html)
https://lhr.uap-bd.edu/lhrfaculty1.php        (Law & Human Rights)
https://www.uap-bd.edu/bsh/faculty.html       (Basic Sciences & Humanities)
https://pharmacy.uap-bd.edu/faculty/<name>.php
"""
from .base_scraper import BaseScraper

DEPARTMENTS = {
    "cse": "Computer Science and Engineering",
    "ce": "Civil Engineering",
    "eee": "Electrical and Electronic Engineering",
    "pharmacy": "Pharmacy",
    "lhr": "Law and Human Rights",
    "law": "Law and Human Rights",
    "arch": "Architecture",
    "architecture": "Architecture",
    "bba": "Business Administration",
    "business": "Business Administration",
    "english": "English",
    "bsh": "Basic Sciences and Humanities",
}
_SUBSITES = ("cse", "ce", "eee", "pharmacy", "lhr", "arch", "bba", "english")


class UAPScraper(BaseScraper):
    key = "uap"
    short_name = "UAP"
    name = "University of Asia Pacific"
    homepage = "https://www.uap-bd.edu"
    allowed_domains = ("uap-bd.edu",)
    start_urls = ("https://www.uap-bd.edu/",) + tuple(f"https://{s}.uap-bd.edu/" for s in _SUBSITES)
    seed_listing_urls = (
        "https://cse.uap-bd.edu/people/faculty/",
        "https://cse.uap-bd.edu/faculty/faculties_list",
        "https://ce.uap-bd.edu/faculty.html",
        "https://ce.uap-bd.edu/faculty_on_leave.html",
        "https://lhr.uap-bd.edu/lhrfaculty1.php",
        "https://www.uap-bd.edu/bsh/faculty.html",
        # Same naming on the other department sites (skipped if missing):
        "https://eee.uap-bd.edu/faculty.html",
        "https://pharmacy.uap-bd.edu/faculty.php",
        "https://arch.uap-bd.edu/faculty.html",
        "https://bba.uap-bd.edu/faculty.html",
        "https://english.uap-bd.edu/faculty.html",
    )
    listing_patterns = (
        r"uap-bd\.edu/(?:[\w-]+/)?faculty(?:_on_leave|_list|[-_]?members?|[-_]full[-_]time|[-_]part[-_]time|\d)?\.(?:html?|php)$",
        r"uap-bd\.edu/people/faculty/?$",
        r"uap-bd\.edu/faculty/faculties_list",
        r"uap-bd\.edu/[\w-]*faculty\d*\.php$",
    )
    follow_patterns = (r"^https?://(?:www\.)?(?:[\w-]+\.)?uap-bd\.edu/(?:[\w-]+/)?(?:index\.(?:html?|php))?$",)
    profile_patterns = (
        r"uap-bd\.edu/people/faculty/[\w.-]+/?$",
        r"uap-bd\.edu/faculty/(?!faculties_list)[\w.-]+\.(?:php|html?)$",
    )
    exclude_patterns = (r"/news-events/", r"/notice", r"\.pdf$")
    department_names = DEPARTMENTS
