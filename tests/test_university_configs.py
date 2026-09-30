"""Checks every university configuration against real URLs taken from the live websites."""
import pytest

from scrapers import SCRAPERS
from utils.http_client import HttpClient

client = HttpClient(user_agent="test")
SCRAPER_OBJECTS = {key: cls(client) for key, cls in SCRAPERS.items()}

# Real faculty list pages (found on the live sites) -> expected department folder.
REAL_LIST_PAGES = [
    ("ewu", "https://fse.ewubd.edu/computer-science-engineering/faculty-members", "Computer Science and Engineering"),
    ("ewu", "https://fbe.ewubd.edu/economics-department/faculty-members", "Economics"),
    ("ewu", "https://flass.ewubd.edu/english-department/faculty-members", "English"),
    ("seu", "https://seu.edu.bd/cse-faculties-staff", "Computer Science and Engineering"),
    ("seu", "https://seu.edu.bd/textile-faculties-staff", "Textile Engineering"),
    ("seu", "https://seu.edu.bd/dept/islamic_studies.php?id=faculty", "Islamic Studies"),
    ("ulab", "https://ulab.edu.bd/people/cse-faculty", "Computer Science and Engineering"),
    ("ulab", "https://ulab.edu.bd/people/ba-faculty?page=2", "Business Administration"),
    ("ulab", "https://deh.ulab.edu.bd/people/deh-faculty", "English and Humanities"),
    ("ulab", "https://eee.ulab.edu.bd/eee/people/bcs-eee-faculty", "Electrical and Electronic Engineering"),
    ("buft", "https://buft.edu.bd/department-of-arts-in-fashion-studies/teaching-staff", "Fashion Studies"),
    ("buft", "https://buft.edu.bd/department-of-knitwear-engineering/teaching-staff", "Knitwear Manufacturing and Technology"),
    ("cub", "https://cse.cub.edu.bd/cse/faculty.php", "Computer Science and Engineering"),
    ("cub", "http://home.cub.edu.bd/cub/faculty.php?TA=FacultyReg", None),
    ("uap", "https://cse.uap-bd.edu/people/faculty/", "Computer Science and Engineering"),
    ("uap", "https://ce.uap-bd.edu/faculty.html", "Civil Engineering"),
    ("uap", "https://ce.uap-bd.edu/faculty_on_leave.html", "Civil Engineering"),
    ("uap", "https://lhr.uap-bd.edu/lhrfaculty1.php", "Law and Human Rights"),
    ("uap", "https://www.uap-bd.edu/bsh/faculty.html", "Basic Sciences and Humanities"),
    ("eub", "https://eub.edu.bd/department-of-ipe/1000/", "Industrial and Production Engineering"),
    ("bubt", "https://bubt.edu.bd/department/department-of-computer-science-engineering/faculty", "Computer Science and Engineering"),
    ("bubt", "https://www.bubt.edu.bd/department/department-of-management/faculty", "Management"),
    ("bubt", "https://www.bubt.edu.bd/home/faculty_member/economics", "Economics"),
    ("bubt", "https://cse.bubt.edu.bd/faculty", "Computer Science and Engineering"),
    ("prime", "https://primeuniversity.ac.bd/department/department-of-english/faculty", "English"),
    ("prime", "https://primeuniversity.ac.bd/department/department-of-electrical-and-electronic-engineering-eee/faculty",
     "Electrical and Electronic Engineering"),
]

# Real individual profile pages found on the live sites.
REAL_PROFILE_PAGES = [
    ("ewu", "https://fse.ewubd.edu/computer-science-engineering/faculty-view/saddam.cse"),
    ("ewu", "https://flass.ewubd.edu/faculty-view/mtanjeela"),
    ("ulab", "https://usb.ulab.edu.bd/faculty/sakib-hossain"),
    ("ulab", "https://usb.ulab.edu.bd/bba/faculty/md-imran-hossain-phd"),
    ("cub", "https://www.cub.edu.bd/faculty_member_details.php?faculty=dr-kazi-abu-taher"),
    ("uap", "https://cse.uap-bd.edu/people/faculty/nnr/"),
    ("uap", "https://pharmacy.uap-bd.edu/faculty/shihab.php"),
    ("eub", "https://www.eub.edu.bd/faculty/faculty-members/vRRs8J39CUfI1Uwbc4x69"),
    ("bubt", "https://bubt.edu.bd/department/department-of-computer-science-engineering/faculty/profile/SJC"),
    ("bubt", "https://www.bubt.edu.bd/department/member_details/145"),
    ("prime", "https://primeuniversity.ac.bd/faculty-profile.php?id=96"),
]


@pytest.mark.parametrize("key,url,department", REAL_LIST_PAGES)
def test_real_list_pages_are_recognised(key, url, department):
    scraper = SCRAPER_OBJECTS[key]
    assert scraper.is_allowed(url)
    assert scraper.is_listing_url(url)
    assert not scraper.is_profile_url(url)
    if department:
        assert scraper.department_for(url) == department


@pytest.mark.parametrize("key,url", REAL_PROFILE_PAGES)
def test_real_profile_pages_are_recognised(key, url):
    scraper = SCRAPER_OBJECTS[key]
    assert scraper.is_allowed(url)
    assert scraper.is_profile_url(url)
    assert not scraper.is_listing_url(url)


@pytest.mark.parametrize("key", list(SCRAPERS))
def test_every_seed_and_start_url_is_usable(key):
    scraper = SCRAPER_OBJECTS[key]
    assert scraper.seed_listing_urls and scraper.start_urls
    for url in scraper.start_urls:
        assert scraper.is_allowed(url), url
    for url in scraper.seed_listing_urls:
        assert scraper.is_allowed(url), url
        assert scraper.is_listing_url(url), url


def test_pages_that_must_not_be_crawled():
    assert not SCRAPER_OBJECTS["bubt"].is_allowed("https://classic.bubt.edu.bd/home/faculty_member/finance")
    assert not SCRAPER_OBJECTS["seu"].is_allowed("https://jobs.seu.edu.bd/")
    assert not SCRAPER_OBJECTS["ulab"].is_allowed("https://ulab.edu.bd/staff/eee-staff")
    assert not SCRAPER_OBJECTS["ewu"].is_allowed("https://www.google.com/")
