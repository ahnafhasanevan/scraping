"""Registry of the university scrapers (key -> class)."""
from .base_scraper import BaseScraper, ScrapeSettings
from .bubt import BUBTScraper
from .buft import BUFTScraper
from .cub import CUBScraper
from .eub import EUBScraper
from .ewu import EWUScraper
from .prime import PrimeScraper
from .seu import SEUScraper
from .uap import UAPScraper
from .ulab import ULABScraper

SCRAPERS = {
    cls.key: cls
    for cls in (EWUScraper, SEUScraper, ULABScraper, BUFTScraper, CUBScraper, UAPScraper, EUBScraper, BUBTScraper, PrimeScraper)
}

__all__ = ["BaseScraper", "ScrapeSettings", "SCRAPERS"]
