"""East West University - faculty lists live on three school sub-sites:
fse (Science & Engineering), fbe (Business & Economics) and flass (Liberal Arts & Social Sciences).
List page:    https://fse.ewubd.edu/computer-science-engineering/faculty-members
Profile page: https://fse.ewubd.edu/computer-science-engineering/faculty-view/taskeed
"""
from .base_scraper import BaseScraper

FSE, FBE, FLASS = "https://fse.ewubd.edu", "https://fbe.ewubd.edu", "https://flass.ewubd.edu"

DEPARTMENTS = {
    "computer-science-engineering": "Computer Science and Engineering",
    "electrical-electronic-engineering": "Electrical and Electronic Engineering",
    "electronics-communications-engineering": "Electronics and Communications Engineering",
    "civil-engineering": "Civil Engineering",
    "genetic-engineering-biotechnology": "Genetic Engineering and Biotechnology",
    "mathematical-physical-science": "Mathematical and Physical Sciences",
    "pharmacy-department": "Pharmacy",
    "business-administration": "Business Administration",
    "economics-department": "Economics",
    "masters-of-business-administration": "MBA and EMBA Programs",
    "english-department": "English",
    "law-department": "Law",
    "sociology-department": "Sociology",
    "social-relations-department": "Social Relations",
    "information-studies-library-management": "Information Studies and Library Management",
}
_SCHOOL_OF = {
    "computer-science-engineering": FSE, "electrical-electronic-engineering": FSE,
    "electronics-communications-engineering": FSE, "civil-engineering": FSE,
    "genetic-engineering-biotechnology": FSE, "mathematical-physical-science": FSE, "pharmacy-department": FSE,
    "business-administration": FBE, "economics-department": FBE, "masters-of-business-administration": FBE,
    "english-department": FLASS, "law-department": FLASS, "sociology-department": FLASS,
    "social-relations-department": FLASS, "information-studies-library-management": FLASS,
}


class EWUScraper(BaseScraper):
    key = "ewu"
    short_name = "EWU"
    name = "East West University"
    homepage = "https://www.ewubd.edu"
    allowed_domains = ("ewubd.edu",)
    start_urls = ("https://www.ewubd.edu/", f"{FSE}/", f"{FBE}/", f"{FLASS}/")
    seed_listing_urls = tuple(f"{school}/{slug}/faculty-members" for slug, school in _SCHOOL_OF.items())
    listing_patterns = (r"ewubd\.edu/[\w-]+/faculty-members/?(?:\?.*)?$",)
    follow_patterns = (r"^https?://(?:fse|fbe|flass)\.ewubd\.edu/[\w-]+/?$",)
    profile_patterns = (r"ewubd\.edu/(?:[\w-]+/)?faculty-view/[^/?#]+",)
    exclude_patterns = (r"/news-details/", r"/achievement", r"/on-going-research", r"/category-courses", r"/events?[/-]")
    department_names = DEPARTMENTS
