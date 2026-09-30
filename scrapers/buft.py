"""BGMEA University of Fashion & Technology.
List page: https://buft.edu.bd/department-of-computer-science-and-engineering/teaching-staff
"""
from .base_scraper import BaseScraper

BASE = "https://buft.edu.bd"

DEPARTMENTS = {
    "department-of-fashion-design-and-technology": "Fashion Design and Technology",
    "department-of-arts-in-fashion-studies": "Fashion Studies",
    "department-of-textile-engineering-and-management": "Textile Engineering and Management",
    "department-of-apparel-merchandising-and-management": "Apparel Merchandising and Management",
    "department-of-knitwear-engineering": "Knitwear Manufacturing and Technology",
    "department-of-industrial-engineering": "Industrial Engineering",
    "department-of-computer-science-and-engineering": "Computer Science and Engineering",
    "department-of-business-administration": "Business Administration",
    "department-of-english": "English",
    "department-of-sciences": "Sciences",
    "department-of-environmental-science": "Environmental Science",
    "buft-institute-of-fashion-and-technology": "BUFT Institute of Fashion and Technology",
    # Not verified - tried in case they exist:
    "department-of-apparel-manufacturing-engineering": "Apparel Manufacturing Engineering",
    "department-of-economics": "Economics",
    "department-of-law": "Law",
}


class BUFTScraper(BaseScraper):
    key = "buft"
    short_name = "BUFT"
    name = "BGMEA University of Fashion & Technology"
    homepage = BASE
    allowed_domains = ("buft.edu.bd",)
    start_urls = (f"{BASE}/",)
    seed_listing_urls = tuple(f"{BASE}/{slug}/teaching-staff" for slug in DEPARTMENTS)
    listing_patterns = (r"buft\.edu\.bd/[\w-]+/teaching-staff/?$",)
    follow_patterns = (r"buft\.edu\.bd/(?:department-of-[\w-]+|faculty-of-[\w-]+|[\w-]*institute[\w-]*)/?$",)
    profile_patterns = (r"buft\.edu\.bd/(?:faculty|teacher|profile|faculty-profile|teaching-staff)/[\w.-]+/?$",)
    exclude_patterns = (r"/contact$", r"/notice", r"/news")
    department_names = DEPARTMENTS
