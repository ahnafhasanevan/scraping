"""The five stand-alone scripts (DIU, UIU, AIUB, IUB, NSU) run unchanged through main.py."""
import csv
import json
from pathlib import Path

import pytest

import external_scrapers
import main
from external_scrapers import EXTERNAL_SCRIPTS, load_script, read_results, redirect_output
from tests.mock_site import MockSite, make_jpeg


@pytest.mark.parametrize("key", list(EXTERNAL_SCRIPTS))
def test_script_loads_and_output_is_redirected(key, tmp_path):
    module = load_script(EXTERNAL_SCRIPTS[key])
    assert callable(module.main)
    redirect_output(module, tmp_path)
    for name in ("OUTPUT_DIR", "SAVE_DIR", "IMAGES_DIR", "CSV_FILE", "JSON_FILE"):
        if hasattr(module, name):
            assert str(getattr(module, name)).startswith(str(tmp_path)), (name, getattr(module, name))


def test_read_results_understands_each_csv_format(tmp_path):
    photo = tmp_path / "Department_of_CSE" / "Jane_Doe.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"x")
    samples = {
        "diu": ("scrape_log.csv", ["faculty", "department", "folder", "name", "designation", "category",
                                   "profile_url", "image_url", "image_path", "status"],
                ["FSIT", "Department of CSE", "Department_of_CSE", "Jane Doe", "Lecturer", "faculty",
                 "https://x/profile/j", "https://x/j.jpg", str(photo), "downloaded"]),
        "uiu": ("scrape_log.csv", ["department_folder", "name", "designation", "email", "profile_url",
                                   "image_url", "image_path", "status"],
                ["Department_of_CSE", "Jane Doe", "Lecturer", "j@uiu.ac.bd", "https://x/j", "https://x/j.jpg",
                 str(photo), "downloaded"]),
        "nsu": ("faculty_photos_index.csv", ["department", "name", "profile_url", "image_url", "saved_file", "status"],
                ["Department_of_CSE", "Jane Doe", "ece:Jane Doe", "https://x/j.jpg",
                 str(Path("Department_of_CSE") / "Jane_Doe.jpg"), "downloaded"]),
    }
    for key, (csv_name, header, row) in samples.items():
        with open(tmp_path / csv_name, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerow(row)
        [record] = read_results(EXTERNAL_SCRIPTS[key], tmp_path, tmp_path)
        assert record.name == "Jane Doe"
        assert record.department in ("Department of CSE",)
        assert record.photo_file == str(Path("Department_of_CSE") / "Jane_Doe.jpg")
        assert record.photo_status == "downloaded"
        (tmp_path / csv_name).unlink()


@pytest.fixture()
def api_site(monkeypatch):
    with MockSite() as site:
        site.files["/aiub.json"] = (json.dumps({"EmployeeProfileLightList": [
            {"CvPersonal": {"Name": "Dr. Aiub Person", "Email": "a@aiub.edu", "UserId": "1"},
             "PersonalOtherInfo": {"SecondProfilePhoto": "/photos/aiub1.jpg"},
             "Faculty": "Faculty of Science and Technology", "HrDepartment": "Department of CS",
             "Designation": "Professor"}]}).encode(), "application/json")
        site.files["/api/iub"] = (json.dumps({"faculties": [
            {"name": "Iub Person", "department": "Computer Science", "position": "Lecturer",
             "email": "i@iub.edu.bd", "slug": "iub-person", "image": site.url + "/photos/iub1.jpg"}],
            "pagination": {"facultyTotal": 1}}).encode(), "application/json")
        for name in ("aiub1", "iub1"):
            site.files[f"/photos/{name}.jpg"] = (make_jpeg((10, 200, 30), (300, 360)), "image/jpeg")

        real_load = external_scrapers.load_script

        def load_with_local_urls(script):  # only the site address changes, never the logic
            module = real_load(script)
            if script.key == "aiub":
                module.JSON_URL, module.BASE_URL = site.url + "/aiub.json", site.url
                module.DOWNLOAD_DELAY = 0
            if script.key == "iub":
                module.BASE_API, module.DOWNLOAD_DELAY = site.url + "/api/iub", 0
            return module

        monkeypatch.setattr(external_scrapers, "load_script", load_with_local_urls)
        yield site


def test_aiub_and_iub_run_through_main(api_site, tmp_path):
    assert main.main(["--university", "aiub", "iub", "--output", str(tmp_path), "--format", "csv"]) == 0
    aiub_photo = (tmp_path / "photos" / "AIUB - American International University-Bangladesh" / "images"
                  / "Faculty of Science and Technology" / "Department of CS" / "Dr. Aiub Person.jpg")
    iub_photo = (tmp_path / "photos" / "IUB - Independent University Bangladesh" / "images"
                 / "Computer Science" / "Iub Person.jpg")
    assert aiub_photo.is_file() and iub_photo.is_file()
    with open(tmp_path / "data" / "processed" / "all_faculty_merged.csv", encoding="utf-8-sig") as handle:
        rows = {r["name"]: r for r in csv.DictReader(handle)}
    assert rows["Dr. Aiub Person"]["university"] == "AIUB"
    assert rows["Dr. Aiub Person"]["designation"] == "Professor"
    assert rows["Iub Person"]["photo_status"] == "downloaded"
    assert (tmp_path / rows["Iub Person"]["photo_file"]).is_file()
