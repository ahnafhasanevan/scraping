"""Download, validate, de-duplicate and save faculty photos."""
from __future__ import annotations

import glob
import hashlib
import io
import shutil
import json
import logging
import os
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .cleaner import name_key, safe_filename
from .http_client import HttpClient
from .models import FacultyRecord

log = logging.getLogger("scraper.images")

try:
    from PIL import Image, ImageOps
except ImportError:  # Pillow is optional; validation then relies on file signatures only
    Image = None
    ImageOps = None

STATUS_DOWNLOADED = "downloaded"
STATUS_EXISTING = "already downloaded"
STATUS_NO_PHOTO = "no photo found"
STATUS_PLACEHOLDER = "placeholder (no real photo)"
STATUS_FAILED = "download failed"
STATUS_INVALID = "not a valid image"
STATUS_TOO_SMALL = "image too small"
STATUS_SKIPPED = "not downloaded (--no-images)"

_SIZE_PARAMS = {"w", "h", "width", "height", "resize", "fit", "crop", "itok", "quality", "q"}


def full_size_variants(url: str) -> list[str]:
    """Candidate URLs of the original picture, best first, ending with the URL itself."""
    variants: list[str] = []
    parts = urlsplit(url)
    path = parts.path
    # WordPress: photo-150x150.jpg -> photo.jpg
    wp_path = re.sub(r"-\d{2,4}x\d{2,4}(?=\.\w{3,4}$)", "", path)
    # Drupal image styles: /files/styles/thumbnail/public/x.jpg -> /files/x.jpg
    drupal_path = re.sub(r"/styles/[^/]+/(public|private)/", "/", path)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _SIZE_PARAMS])
    for new_path in (wp_path, drupal_path):
        if new_path != path:
            variants.append(urlunsplit((parts.scheme, parts.netloc, new_path, query, "")))
    variants.append(url)
    return list(dict.fromkeys(variants))


def sniff_extension(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM":
        return ".bmp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return ".avif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1"):
        return ".heic"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tif"
    return None


@dataclass
class _Result:
    status: str
    data: bytes = b""
    extension: str = ""
    sha1: str = ""
    final_url: str = ""
    existing_file: Optional[Path] = None


_PHOTO_SUFFIXES = (".jpg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic", ".tif")


def with_extension(target: Path, extension: str) -> Path:
    """Append an extension. (Path.with_suffix would turn 'Md. Rafiq Islam' into 'Md.jpg'.)"""
    return target.parent / (target.name + extension)


def _siblings_with_other_extension(target: Path) -> list[Path]:
    if not target.parent.exists():
        return []
    return [
        p for p in target.parent.glob(glob.escape(target.name) + ".*")
        if p.suffix.lower() in _PHOTO_SUFFIXES and p.name == target.name + p.suffix
    ]


class ImageDownloader:
    def __init__(self, client: HttpClient, output_dir: Path, photos_dir: Path, manifest_path: Path,
                 min_bytes: int = 1500, min_side: int = 60, convert_to_jpg: bool = False,
                 workers: int = 4, placeholder_threshold: int = 3, show_progress: bool = True):
        self.client = client
        self.output_dir = output_dir
        self.photos_dir = photos_dir
        self.manifest_path = manifest_path
        self.min_bytes = min_bytes
        self.min_side = min_side
        self.convert_to_jpg = convert_to_jpg
        self.workers = max(1, workers)
        self.placeholder_threshold = max(2, placeholder_threshold)
        self.show_progress = show_progress
        self._lock = threading.Lock()
        self.manifest: dict[str, dict] = {}
        if manifest_path.exists():
            try:
                self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.manifest = {}

    # ------------------------------------------------------------------ public
    def process(self, records: list[FacultyRecord], university_folder: str) -> None:
        """Download photos for one university and fill photo_file / photo_status."""
        targets = self._assign_paths(records, university_folder)
        by_url: dict[str, list[FacultyRecord]] = defaultdict(list)
        for record in records:
            if record.photo_url:
                by_url[record.photo_url].append(record)
            elif not record.photo_status:
                record.photo_status = STATUS_NO_PHOTO

        results: dict[str, _Result] = {}
        pending = []
        for url, owners in by_url.items():
            reused = self._from_manifest(url, targets[id(owners[0])])
            if reused is not None:
                results[url] = reused
            else:
                pending.append((url, owners[0].source_page or owners[0].profile_url))

        progress = None
        if self.show_progress and pending:
            try:
                from tqdm import tqdm
                progress = tqdm(total=len(pending), desc=f"  photos {university_folder[:24]}", unit="img", leave=False)
            except ImportError:
                progress = None
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._fetch, url, referer): url for url, referer in pending}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    results[url] = future.result()
                except Exception as exc:  # never let one photo stop the run
                    log.debug("Photo %s failed: %s", url, exc)
                    results[url] = _Result(STATUS_FAILED)
                if progress:
                    progress.update(1)
        if progress:
            progress.close()

        # The same picture used for many different people is a "no photo" placeholder.
        people_by_hash: dict[str, set[str]] = defaultdict(set)
        for url, result in results.items():
            if result.sha1:
                for owner in by_url[url]:
                    people_by_hash[result.sha1].add(name_key(owner.name))
        placeholders = {h for h, people in people_by_hash.items() if len(people) >= self.placeholder_threshold}

        for url, owners in by_url.items():
            result = results.get(url, _Result(STATUS_FAILED))
            for record in owners:
                target = targets[id(record)]
                if result.sha1 in placeholders:
                    record.photo_status = STATUS_PLACEHOLDER
                    self._remove_existing(target)
                    continue
                if result.status not in (STATUS_DOWNLOADED, STATUS_EXISTING):
                    record.photo_status = result.status
                    continue
                path = with_extension(target, result.extension)
                if result.data:
                    self._write(target, path, result.data)
                elif result.existing_file is not None and result.existing_file != path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(result.existing_file, path)
                record.photo_file = self._relative(path)
                record.photo_status = result.status
                with self._lock:
                    self.manifest[url] = {"file": record.photo_file, "sha1": result.sha1}
        self.save_manifest()

    def save_manifest(self) -> None:
        try:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.manifest_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.manifest, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.manifest_path)
        except OSError as exc:
            log.debug("Could not save image manifest: %s", exc)

    # ------------------------------------------------------------------ helpers
    def _assign_paths(self, records: list[FacultyRecord], university_folder: str) -> dict[int, Path]:
        """<photos>/<University>/<Department>/<Name> (extension added after download)."""
        targets: dict[int, Path] = {}
        used: dict[str, str] = {}
        root = self.photos_dir / safe_filename(university_folder, 45)
        for record in records:
            folder = root / safe_filename(record.department or "Other", 55)
            base = safe_filename(record.name, 80)
            identity = record.photo_url or record.profile_url or record.name
            candidate, counter = base, 2
            while str(folder / candidate).lower() in used and used[str(folder / candidate).lower()] != identity:
                candidate = f"{base} ({counter})"
                counter += 1
            used[str(folder / candidate).lower()] = identity
            targets[id(record)] = folder / candidate
        return targets

    def _from_manifest(self, url: str, target: Path) -> Optional[_Result]:
        entry = self.manifest.get(url)
        if not entry:
            return None
        path = self.output_dir / entry.get("file", "")
        if not entry.get("file") or not path.is_file() or path != with_extension(target, path.suffix):
            return None
        return _Result(STATUS_EXISTING, extension=path.suffix, sha1=entry.get("sha1", ""), existing_file=path)

    def _fetch(self, url: str, referer: str) -> _Result:
        last_status = STATUS_FAILED
        for candidate in full_size_variants(url):
            resp = self.client.get_binary(candidate, referer=referer or None)
            if resp is None:
                continue
            result = self._validate(resp.content)
            if result.status == STATUS_DOWNLOADED:
                result.final_url = candidate
                return result
            last_status = result.status
        return _Result(last_status)

    def _validate(self, data: bytes) -> _Result:
        extension = sniff_extension(data)
        if not extension:
            return _Result(STATUS_INVALID)
        if len(data) < self.min_bytes:
            return _Result(STATUS_TOO_SMALL)
        if Image is not None:
            try:
                with Image.open(io.BytesIO(data)) as image:
                    width, height = image.size
                    if min(width, height) < self.min_side:
                        return _Result(STATUS_TOO_SMALL)
                    if self.convert_to_jpg and extension != ".jpg":
                        data, extension = self._to_jpeg(image), ".jpg"
            except Exception:
                if extension not in (".avif", ".heic"):  # Pillow may lack these codecs
                    return _Result(STATUS_INVALID)
        return _Result(STATUS_DOWNLOADED, data=data, extension=extension, sha1=hashlib.sha1(data).hexdigest())

    @staticmethod
    def _to_jpeg(image) -> bytes:
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=92, optimize=True)
        return buffer.getvalue()

    def _write(self, target: Path, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        for other in _siblings_with_other_extension(target):  # a previous run saved another format
            if other != path:
                try:
                    other.unlink()
                except OSError:
                    pass

    def _remove_existing(self, target: Path) -> None:
        for other in _siblings_with_other_extension(target):
            try:
                other.unlink()
            except OSError:
                pass

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.output_dir))
        except ValueError:
            return str(path)
