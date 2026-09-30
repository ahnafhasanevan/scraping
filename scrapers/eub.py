"""European University of Bangladesh (modern JavaScript site).
Department page (lists its faculty): https://eub.edu.bd/department-of-ipe/1000/
Profile page:                        https://eub.edu.bd/faculty/faculty-members/<id>
Data embedded as JSON (Next.js) is read directly; otherwise pages are rendered with a
headless browser automatically.
"""
from .base_scraper import BaseScraper

DEPARTMENTS = {
    "ipe": "Industrial and Production Engineering",
    "cse": "Computer Science and Engineering",
    "eee": "Electrical and Electronic Engineering",
    "civil": "Civil Engineering",
    "ce": "Civil Engineering",
    "textile": "Textile Engineering",
    "te": "Textile Engineering",
    "me": "Mechanical Engineering",
    "mechanical": "Mechanical Engineering",
    "bba": "Business Administration",
    "business-administration": "Business Administration",
    "law": "Law",
    "english": "English",
    "thm": "Tourism and Hospitality Management",
    "economics": "Economics",
    "mathematics": "Mathematics",
    "math": "Mathematics",
    "mth": "Mathematics",
}


class EUBScraper(BaseScraper):
    key = "eub"
    short_name = "EUB"
    name = "European University of Bangladesh"
    homepage = "https://eub.edu.bd"
    allowed_domains = ("eub.edu.bd",)
    start_urls = ("https://eub.edu.bd/",)
    seed_listing_urls = ("https://eub.edu.bd/department-of-ipe/1000/", "https://eub.edu.bd/faculty/faculty-members")
    listing_patterns = (
        r"eub\.edu\.bd/department-of-[\w-]+/\d+/?$",
        r"eub\.edu\.bd/faculty/faculty-members/?$",
        r"eub\.edu\.bd/[\w-]+/faculty(?:-members)?/?$",
    )
    follow_patterns = (
        r"eub\.edu\.bd/(?:bachelor|master|bsc|ba|bba|mba|llb|llm|msc|b-sc|m-sc)[\w-]*/?$",
        r"eub\.edu\.bd/faculty-of-[\w-]+",
        r"eub\.edu\.bd/departments?/?$",
    )
    profile_patterns = (r"eub\.edu\.bd/faculty/faculty-members/[\w-]{8,}/?$",)
    exclude_patterns = (r"/alumni-industry", r"/notice", r"/news", r"/events?/")
    department_names = DEPARTMENTS
