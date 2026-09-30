"""Write faculty records to CSV / JSON / Excel."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from .models import COLUMNS, FacultyRecord

log = logging.getLogger("scraper.export")


def save_records(records: Iterable[FacultyRecord], base_path: Path, formats: Iterable[str]) -> list[Path]:
    """Save records as <base_path>.csv/.json/.xlsx. Returns the written paths."""
    frame = pd.DataFrame([r.to_dict() for r in records], columns=COLUMNS)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        path = base_path.with_suffix(f".{fmt}")
        try:
            if fmt == "csv":
                frame.to_csv(path, index=False, encoding="utf-8-sig")  # BOM keeps Excel happy
            elif fmt == "json":
                frame.to_json(path, orient="records", indent=2, force_ascii=False)
            elif fmt == "xlsx":
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    frame.to_excel(writer, index=False, sheet_name="Faculty")
                    sheet = writer.sheets["Faculty"]
                    sheet.freeze_panes = "A2"
                    for column_cells in sheet.columns:
                        longest = max((len(str(c.value)) for c in column_cells if c.value is not None), default=8)
                        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(10, longest + 2), 60)
            else:
                continue
        except PermissionError:
            log.error("Cannot write %s - is it open in Excel? Close it and run again.", path)
            continue
        written.append(path)
    return written
