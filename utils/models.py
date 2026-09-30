"""Data model shared by all scrapers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class FacultyRecord:
    university: str                 # short name, e.g. "EWU"
    university_name: str            # e.g. "East West University"
    department: str
    name: str
    designation: str = ""
    qualifications: str = ""
    email: str = ""
    phone: str = ""
    research_interests: str = ""
    profile_url: str = ""
    photo_url: str = ""
    source_page: str = ""
    photo_file: str = ""            # path of the saved photo, relative to the output folder
    photo_status: str = ""

    def fill_missing(self, data: dict) -> None:
        """Copy values from another record/dict into fields that are still empty."""
        for field in fields(self):
            value = data.get(field.name) if isinstance(data, dict) else getattr(data, field.name, "")
            if value and not getattr(self, field.name):
                setattr(self, field.name, value)

    def to_dict(self) -> dict:
        return asdict(self)


COLUMNS = [f.name for f in fields(FacultyRecord)]
