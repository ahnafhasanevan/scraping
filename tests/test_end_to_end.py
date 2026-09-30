"""Runs the full pipeline (discovery -> extraction -> profiles -> photos -> CSV/XLSX/JSON)
against the mock university website in tests/mock_site.py."""
import csv
import json

import pytest
from PIL import Image

import config
import main
from scrapers import SCRAPERS, BaseScraper
from tests.mock_site import MockSite


@pytest.fixture()
def site(monkeypatch):
    monkeypatch.setattr(config, "IMAGE_DELAY", 0)
    with MockSite() as mock:
        class MockScraper(BaseScraper):
            key = "mock"
            short_name = "MOCK"
            name = "Mock University"
            homepage = mock.url
            allowed_domains = ("127.0.0.1",)
            start_urls = (mock.url + "/",)
            # Guessed list pages: missing (404), a soft 404, and one redirecting to the home page.
            seed_listing_urls = tuple(mock.url + p for p in (
                "/department-of-physics/faculty-members", "/department-of-math/faculty-members",
                "/department-of-chemistry/faculty-members"))
            profile_patterns = (r"/faculty-view/[\w-]+",)
            department_names = {"department-of-cse": "Computer Science and Engineering",
                                "department-of-math": "Mathematics", "department-of-chemistry": "Chemistry"}

        monkeypatch.setitem(SCRAPERS, "mock", MockScraper)
        yield mock


def run(tmp_path):
    return main.main(["--university", "mock", "--output", str(tmp_path), "--delay", "0",
                      "--render", "never", "--format", "all"])


def load_rows(tmp_path):
    with open(tmp_path / "data" / "raw" / "mock_faculty.csv", encoding="utf-8-sig") as handle:
        return {row["name"]: row for row in csv.DictReader(handle)}


def test_full_pipeline(site, tmp_path):
    assert run(tmp_path) == 0
    rows = load_rows(tmp_path)

    expected = {
        "Dr. Abdur Rahman": "Computer Science and Engineering",
        "Dr. Fazlul Karim": "Computer Science and Engineering",
        "Ms. Nasrin Akter": "Computer Science and Engineering",
        "Md. Mahmudul Hasan": "Computer Science and Engineering",
        "Tahmina Islam": "Computer Science and Engineering",          # page 2 (pagination)
        "Sadia Chowdhury": "Computer Science and Engineering",        # photo only on profile page
        "Dr. Iftekhar Anam": "Electrical and Electronic Engineering",  # table layout
        "Dr. Afifa Tamanna": "Electrical and Electronic Engineering",
        "Professor Dr. Parvez Ahmed": "Law",                          # flat layout
        "Abdullah Al Jahid": "Law",
        "Nazifa Muniyat Quader": "Law",                               # names-only link -> profile
        "Dr. Kohinoor Sultana": "Law",                                # "View Profile" link -> profile
        "Rezina Sultana": "English",
        "Shahbaz Khan": "English",
        "Arifa Rahman": "English",
        "Moriam Quadir": "English",
        "Benazir Rahman": "Business Administration",                  # Next.js JSON
        "Zahurul Alam": "Business Administration",
    }
    assert set(rows) == set(expected), sorted(set(rows) ^ set(expected))
    for name, department in expected.items():
        assert rows[name]["department"] == department, name

    # Excluded: soft-404 page, guessed URL that redirected home, robots.txt page, non-academic staff.
    assert not any("Wrong Person" in name for name in rows)
    assert "Prof. Dr. Vice Person" not in rows
    assert "/department-of-chemistry/faculty-members" in site.requests
    assert "Dr. Secret Person" not in rows
    assert "/private/faculty-members" not in site.requests
    assert "Md. Kamal Hossain" not in rows

    assert rows["Ms. Nasrin Akter"]["designation"] == "Assistant Professor"
    assert rows["Dr. Abdur Rahman"]["email"] == "rahman@mock.edu"
    assert rows["Dr. Iftekhar Anam"]["qualifications"].startswith("Ph.D., Texas A&M")

    saved = {name: row for name, row in rows.items() if row["photo_file"]}
    placeholders = {name for name, row in rows.items() if row["photo_status"].startswith("placeholder")}
    assert placeholders == {"Rezina Sultana", "Shahbaz Khan", "Arifa Rahman"}
    assert set(saved) == set(expected) - placeholders

    for name, row in saved.items():
        path = tmp_path / row["photo_file"]
        assert path.is_file(), path
        assert path.name.startswith(name), path.name       # "Md. Mahmudul Hasan.jpg", not "Md.jpg"
        with Image.open(path) as image:
            assert image.size == (400, 480) or name in ("Moriam Quadir",), (name, image.size)

    # Thumbnail upgraded to the full-size original, JS-proxy URL unwrapped, profile photo used.
    assert rows["Dr. Abdur Rahman"]["photo_url"].endswith("rahman-150x150.jpg")
    assert rows["Zahurul Alam"]["photo_url"].endswith("/uploads/bba/zahurul.jpg")
    assert rows["Sadia Chowdhury"]["photo_url"].endswith("chowdhury-real.jpg")
    photo = tmp_path / rows["Md. Mahmudul Hasan"]["photo_file"]
    assert photo.parent.name == "Computer Science and Engineering"
    assert photo.parent.parent.name == "MOCK - Mock University"

    # Every requested format was written, plus the merged dataset.
    for ext in ("csv", "json", "xlsx"):
        assert (tmp_path / "data" / "raw" / f"mock_faculty.{ext}").is_file()
        assert (tmp_path / "data" / "processed" / f"all_faculty_merged.{ext}").is_file()
    merged = json.loads((tmp_path / "data" / "processed" / "all_faculty_merged.json").read_text(encoding="utf-8"))
    assert len(merged) == len(expected)
    assert (tmp_path / "logs" / "scraper.log").is_file()


def test_second_run_reuses_downloaded_photos(site, tmp_path):
    assert run(tmp_path) == 0
    first = load_rows(tmp_path)
    image_requests = sum(1 for r in site.requests if r.endswith(".jpg"))
    assert run(tmp_path) == 0
    second = load_rows(tmp_path)
    assert {n: r["photo_file"] for n, r in first.items()} == {n: r["photo_file"] for n, r in second.items()}
    assert {r["photo_status"] for r in second.values() if r["photo_file"]} == {"already downloaded"}
    # Only the placeholder pictures (not saved) are fetched again.
    assert sum(1 for r in site.requests if r.endswith(".jpg")) - image_requests <= 3
