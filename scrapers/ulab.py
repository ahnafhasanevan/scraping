"""University of Liberal Arts Bangladesh (Drupal site with department sub-sites).
List pages: https://ulab.edu.bd/people/cse-faculty  (paged with ?page=N)
            https://deh.ulab.edu.bd/people/deh-faculty, https://ged.ulab.edu.bd/people/ged-faculty
School of Business: https://usb.ulab.edu.bd/faculty/<name>
"""
from .base_scraper import BaseScraper

DEPARTMENTS = {
    "cse": "Computer Science and Engineering",
    "eee": "Electrical and Electronic Engineering",
    "bcs-eee": "Electrical and Electronic Engineering",
    "ete": "Electronics and Telecommunication Engineering",
    "ba": "Business Administration",
    "bba": "Business Administration",
    "mba": "Business Administration",
    "usb": "Business Administration",
    "deh": "English and Humanities",
    "ged": "General Education",
    "msj": "Media Studies and Journalism",
    "bll": "Bangla Language and Literature",
}


class ULABScraper(BaseScraper):
    key = "ulab"
    short_name = "ULAB"
    name = "University of Liberal Arts Bangladesh"
    homepage = "https://ulab.edu.bd"
    allowed_domains = ("ulab.edu.bd",)
    start_urls = (
        "https://ulab.edu.bd/",
        "https://usb.ulab.edu.bd/",
        "https://eee.ulab.edu.bd/",
        "https://ged.ulab.edu.bd/",
        "https://deh.ulab.edu.bd/",
    )
    seed_listing_urls = (
        "https://ulab.edu.bd/faculty-members-0",
        "https://ulab.edu.bd/people/cse-faculty",
        "https://ulab.edu.bd/people/eee-faculty",
        "https://ulab.edu.bd/people/ba-faculty",
        "https://eee.ulab.edu.bd/people/eee-faculty",
        "https://ete.ulab.edu.bd/people/ete-faculty",
        "https://ged.ulab.edu.bd/people/ged-faculty",
        "https://deh.ulab.edu.bd/people/deh-faculty",
        "https://ulab.edu.bd/people/msj-faculty",
        "https://ulab.edu.bd/people/bll-faculty",
        "https://usb.ulab.edu.bd/faculty/",
    )
    listing_patterns = (
        r"/people/[\w-]*facult(?:y|ies)/?(?:\?page=\d+)?$",
        r"ulab\.edu\.bd/faculty-members(?:-\d+)?/?(?:\?page=\d+)?$",
        r"usb\.ulab\.edu\.bd/(?:[\w-]+/)?faculty/?$",
    )
    follow_patterns = (
        r"ulab\.edu\.bd/department-[\w-]+/?$",
        r"^https?://(?:eee|ete|ged|deh|usb|msj|bll|cse)\.ulab\.edu\.bd/?$",
    )
    profile_patterns = (
        r"usb\.ulab\.edu\.bd/(?:[\w-]+/)?faculty/[\w-]+/?$",
        r"ulab\.edu\.bd/faculty/[\w-]+-[\w-]+/?$",
    )
    exclude_patterns = (r"/staff/", r"/user/", r"/node/\d+/edit")
    department_names = DEPARTMENTS
