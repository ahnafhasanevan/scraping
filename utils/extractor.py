"""Layout-independent extraction of faculty members from listing and profile pages.

Instead of hard-coding CSS selectors (which break whenever a site is redesigned), the
extractor looks for the structure every faculty list shares: a portrait image grouped
with a person's name and usually a designation, repeated for every member.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Iterable, Optional, Pattern, Sequence
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag

from .cleaner import (
    ACADEMIC_RE,
    EMAIL_RE,
    STRONG_ACADEMIC_RE,
    clean_name,
    clean_text,
    extract_degrees,
    extract_emails,
    extract_phone,
    extract_research_interests,
    looks_like_designation,
    looks_like_name,
    name_key,
    normalize_designation,
    text_lines,
)
from .html_tools import (
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    absolute_url,
    attr_tokens,
    canonical_url,
    chrome_container_ids,
    collect_image_nodes,
    in_containers,
    is_junk_url,
    is_placeholder_image,
    is_social_or_external_profile,
    meta_content,
    page_links,
    page_title,
    tokens,
    url_extension,
)

FIELDS = ("name", "designation", "department_hint", "email", "phone", "qualifications",
          "research_interests", "profile_url", "photo_url")

_NAME_TOKENS = {"name", "fullname", "title", "heading", "membername", "facultyname"}
_DESIG_TOKENS = {"designation", "position", "role", "post", "rank", "job", "jobtitle", "subtitle", "desig"}
_PROFILE_CONTAINER_TOKENS = {
    "profile", "faculty", "member", "teacher", "avatar", "photo", "person", "author", "bio", "team",
    "staff", "people", "user", "pic", "picture", "image", "img", "thumb", "thumbnail", "portrait",
}
_PROFILE_LINK_TEXT = {
    "view profile", "profile", "details", "view details", "read more", "more", "see profile",
    "view more", "full profile", "know more", "see more", "bio", "biography", "view", "more info",
    "details »", "read more »", "view profile »", "see details",
}
_PHOTO_URL_HINT_RE = re.compile(
    r"faculty|teacher|staff|member|people|profile|avatar|photo|employee|person|team|upload|storage|media|images?/", re.I)
_PROFILE_PATH_HINT_RE = re.compile(
    r"(faculty|profile|people|member|teacher|staff|person|employee|team)[^?#]*[/=][\w.%-]+/?$"
    r"|faculty[-_]?(view|details?|profile)", re.I)
_DEPT_RE = re.compile(r"\b(?:Department|Dept\.?)\s+of\s+([A-Z][A-Za-z&.,\- ]{1,80}?)\s*(?:$|[;|()\n]|,\s|\s[-–]\s)")
_HONORIFIC_HINT_RE = re.compile(r"^(prof|dr|engr|professor)\b", re.I)


def unwrap_image_proxy(url: str) -> str:
    """'/_next/image?url=%2Fuploads%2Fa.jpg&w=640' -> '/uploads/a.jpg' (full size original)."""
    parts = urlsplit(url)
    if parts.path.endswith("/_next/image"):
        inner = parse_qs(parts.query).get("url", [""])[0]
        if inner:
            return urljoin(url, unquote(inner))
    match = re.match(r"^/_ipx/[^/]+(/.+)$", parts.path)
    if match:
        return urljoin(url, match.group(1))
    return url


def _identity(url: str) -> str:
    """Treat thumbnail and full-size variants of the same picture as one image."""
    path = urlsplit(url).path.lower()
    return re.sub(r"[-_]\d{2,4}x\d{2,4}(?=\.\w+$)", "", path)


def _empty_record() -> dict:
    return {field: "" for field in FIELDS}


# ---------------------------------------------------------------------------------------
# Listing pages: repeated "cards"
# ---------------------------------------------------------------------------------------


class _TextCache:
    def __init__(self):
        self._lengths: dict[int, int] = {}

    def length(self, tag: Tag) -> int:
        key = id(tag)
        if key not in self._lengths:
            self._lengths[key] = len(tag.get_text(" ", strip=True))
        return self._lengths[key]


def _find_card(node: Tag, counts: dict[int, set], cache: _TextCache, max_levels: int = 8, max_text: int = 1500) -> Tag:
    """Largest ancestor of an image that contains no other portrait."""
    card = node
    for level, ancestor in enumerate(node.parents):
        if ancestor.name in (None, "[document]", "html", "body", "main") or level >= max_levels:
            break
        if len(counts.get(id(ancestor), ())) > 1:
            break
        card = ancestor
        if cache.length(ancestor) > max_text:
            break
    return card


def _sibling_lines(card: Tag, image_ancestors: dict[int, set], forward: bool = True) -> list[str]:
    """Text of neighbouring siblings for flat layouts: <img><h4>Name</h4><p>Title</p><img>..."""
    lines: list[str] = []
    siblings = card.next_siblings if forward else card.previous_siblings
    for count, sibling in enumerate(siblings):
        if count > 8 or sum(len(x) for x in lines) > 400:
            break
        if isinstance(sibling, NavigableString):
            lines.extend(text_lines(str(sibling)))
            continue
        if not isinstance(sibling, Tag):
            continue
        if id(sibling) in image_ancestors or sibling.name in ("img", "hr"):
            break
        new = text_lines(sibling.get_text("\n", strip=True))
        lines.extend(new if forward else list(reversed(new)))
    return lines if forward else list(reversed(lines))


def _clean_alt(value: str) -> str:
    value = re.sub(r"\.(jpe?g|png|webp|gif)$", "", value or "", flags=re.I)
    value = re.sub(r"^(photo|image|picture|profile\s*(picture|photo)?|pic)\s*(of)?\s*[:\-]?\s*", "", value, flags=re.I)
    value = re.sub(r"[_]+|(?<=\w)-(?=\w)", " ", value)
    value = clean_text(value)
    return value.title() if value.islower() else value


def _name_candidates(card: Optional[Tag], img: Tag, lines: Sequence[str]) -> Iterable[tuple[str, bool, int]]:
    """(text, strict, strength) in order of trust."""
    elements = card.find_all(True) if card is not None else []
    for el in elements:
        el_tokens = attr_tokens(el)
        if el_tokens & _NAME_TOKENS and not el_tokens & _DESIG_TOKENS:
            yield el.get_text(" ", strip=True), False, 3
            first = text_lines(el.get_text("\n", strip=True))[:1]
            if first:
                yield first[0], False, 3
    for el in (card.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]) if card is not None else []):
        yield el.get_text(" ", strip=True), False, 3
        first = text_lines(el.get_text("\n", strip=True))[:1]
        if first:
            yield first[0], False, 3
    for el in (card.find_all(["a", "strong", "b"]) if card is not None else []):
        yield el.get_text(" ", strip=True), True, 2
    for line in lines:
        yield line, True, 1
    for attr in ("alt", "title"):
        if img.get(attr):
            yield _clean_alt(img.get(attr)), True, 1


def _pick_name(card: Optional[Tag], img: Tag, lines: Sequence[str]) -> tuple[str, int]:
    for text, strict, strength in _name_candidates(card, img, lines):
        name = clean_name(text)
        if looks_like_name(name, strict=strict):
            return name, strength
    return "", 0


def _pick_designation(card: Optional[Tag], lines: Sequence[str], name: str) -> str:
    if card is not None:
        for el in card.find_all(True):
            if attr_tokens(el) & _DESIG_TOKENS:
                value = clean_text(el.get_text(" ", strip=True))
                if value and value != name and len(value) <= 140 and not looks_like_name(value):
                    return normalize_designation(value)
    usable = [l for l in lines if l != name and len(l) <= 140 and not EMAIL_RE.search(l)]
    for pattern in (STRONG_ACADEMIC_RE, ACADEMIC_RE):
        for line in usable:
            if pattern.search(line) and not looks_like_name(line):
                return normalize_designation(line)
    for line in usable:
        if looks_like_designation(line) and not looks_like_name(line):
            return normalize_designation(line)
    return ""


def _split_designation(designation: str) -> tuple[str, str]:
    """'Lecturer, Department of CSE' -> ('Lecturer', 'CSE')."""
    match = re.search(r"[,|\-–]?\s*(?:Department|Dept\.?)\s+of\s+(.+)$", designation, re.I)
    if match and match.start() > 0:
        return designation[: match.start()].strip(" ,|-–"), clean_text(match.group(1))
    return designation, ""


def _department_hint(lines: Sequence[str]) -> str:
    for line in lines:
        match = _DEPT_RE.search(line + "\n")
        if match:
            return clean_text(match.group(1)).strip(" ,.-")
    return ""


def _emails_in(card: Optional[Tag], text: str) -> str:
    emails: list[str] = []
    if card is not None:
        for a in card.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                emails.extend(extract_emails(unquote(href[7:].split("?")[0])))
    emails.extend(extract_emails(text))
    return next(iter(dict.fromkeys(emails)), "")


def _pick_links(card: Optional[Tag], img: Tag, page_url: str, name: str,
                profile_res: Sequence[Pattern]) -> tuple[str, str]:
    """(profile_url, full_size_photo_url) from the anchors of a card."""
    anchors: list[Tag] = []
    wrapping = img.find_parent("a")
    if wrapping is not None:
        anchors.append(wrapping)
    if card is not None:
        if card.name == "a":
            anchors.append(card)
        anchors.extend(card.find_all("a", href=True))
    page_key = canonical_url(page_url)
    best_url, best_score, big_photo = "", 0, ""
    for a in anchors:
        url = absolute_url(a.get("href"), page_url)
        if not url or canonical_url(url) == page_key or is_social_or_external_profile(url):
            continue
        ext = url_extension(url)
        if ext in IMAGE_EXTENSIONS:
            big_photo = big_photo or url
            continue
        if ext in DOCUMENT_EXTENSIONS:
            continue
        text = clean_text(a.get_text(" ", strip=True))
        score = 0
        if any(p.search(url) for p in profile_res):
            score += 5
        if a is wrapping:
            score += 2
        if name and clean_name(text) == name:
            score += 3
        if text.lower() in _PROFILE_LINK_TEXT:
            score += 2
        if _PROFILE_PATH_HINT_RE.search(urlsplit(url).path + ("?" + urlsplit(url).query if urlsplit(url).query else "")):
            score += 1
        if score > best_score:
            best_url, best_score = url, score
    return best_url, big_photo


def _signature(card: Tag, img: Tag) -> tuple:
    path = []
    node = img
    while node is not None and node is not card:
        path.append(node.name)
        node = node.parent
    classes = card.get("class") or []
    return (card.name, tuple(sorted(classes if isinstance(classes, list) else [classes])), tuple(path))


def extract_cards(soup: BeautifulSoup, page_url: str, lenient: bool = True,
                  profile_res: Sequence[Pattern] = ()) -> list[dict]:
    """Find every 'photo + name (+ designation)' group on a page."""
    nodes = collect_image_nodes(soup, page_url)
    if not nodes:
        return []
    counts: dict[int, set] = defaultdict(set)
    for tag, url in nodes:
        identity = _identity(url)
        counts[id(tag)].add(identity)
        for ancestor in tag.parents:
            counts[id(ancestor)].add(identity)
    cache = _TextCache()
    drafts = []
    for tag, url in nodes:
        card = _find_card(tag, counts, cache)
        card_el = card if card is not tag else None
        lines = text_lines(card.get_text("\n", strip=True)) if card_el is not None else []
        name, strength = _pick_name(card_el, tag, lines)
        if not name:  # flat layout: text lives in the following (or preceding) siblings
            for forward in (True, False):
                extra = _sibling_lines(card, counts, forward)
                name, strength = _pick_name(None, tag, extra)
                if name:
                    lines = lines + extra
                    break
        if not name:
            continue
        drafts.append((tag, url, card, card_el, lines, name, strength))

    groups: dict[tuple, int] = defaultdict(int)
    for tag, _, card, *_ in drafts:
        groups[_signature(card, tag)] += 1

    records = []
    for tag, url, card, card_el, lines, name, strength in drafts:
        text = "\n".join(lines)
        designation = _pick_designation(card_el, lines, name)
        designation, dept_from_designation = _split_designation(designation)
        profile_url, big_photo = _pick_links(card_el, tag, page_url, name, profile_res)
        photo = unwrap_image_proxy(big_photo or url)
        record = _empty_record()
        record.update(
            name=name,
            designation=designation,
            department_hint=dept_from_designation or _department_hint(lines),
            email=_emails_in(card_el, text),
            phone=extract_phone(text),
            qualifications=extract_degrees(lines, skip=(name, designation)),
            research_interests=extract_research_interests(text),
            profile_url=profile_url,
            photo_url="" if is_placeholder_image(photo) else photo,
        )
        score = 0
        score += 3 if designation else 0
        score += 1 if record["email"] else 0
        score += 1 if profile_url else 0
        score += 1 if strength >= 3 else 0
        score += 1 if _HONORIFIC_HINT_RE.search(name) else 0
        score += 1 if _PHOTO_URL_HINT_RE.search(urlsplit(url).path) else 0
        score += 2 if groups[_signature(card, tag)] >= 3 else 0
        if score >= 3 or (lenient and score >= 1):
            records.append(record)
    return records


# ---------------------------------------------------------------------------------------
# Listing pages: plain tables without photos
# ---------------------------------------------------------------------------------------


def extract_table_rows(soup: BeautifulSoup, page_url: str) -> list[dict]:
    records = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2:
            continue
        texts = [clean_text(c.get_text(" ", strip=True)) for c in cells]
        name_index = next((i for i, t in enumerate(texts) if looks_like_name(t)), None)
        if name_index is None:
            continue
        designation = next((t for i, t in enumerate(texts) if i != name_index and looks_like_designation(t)), "")
        if not designation:
            continue
        record = _empty_record()
        link = cells[name_index].find("a", href=True)
        profile = absolute_url(link["href"], page_url) if link else ""
        if profile and (url_extension(profile) in IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS
                        or is_social_or_external_profile(profile)):
            profile = ""
        row_text = "\n".join(texts)
        record.update(
            name=clean_name(texts[name_index]),
            designation=normalize_designation(designation),
            email=_emails_in(row, row_text),
            phone=extract_phone(row_text),
            profile_url=profile,
        )
        records.append(record)
    return records


# ---------------------------------------------------------------------------------------
# Data embedded as JSON (Next.js, Nuxt, Inertia/Laravel, JSON-LD, ...)
# ---------------------------------------------------------------------------------------

_NAME_KEYS = ("name", "full_name", "fullname", "fullName", "faculty_name", "facultyName", "teacher_name",
              "teacherName", "employee_name", "employeeName", "name_en", "nameEn", "en_name",
              "display_name", "displayName", "title")
_IMAGE_KEYS = ("image", "photo", "picture", "avatar", "img", "profile_pic", "profilePic", "profile_photo",
               "profilePhoto", "profile_image", "profileImage", "photo_url", "photoUrl", "image_url",
               "imageUrl", "thumbnail", "thumb", "featured_image", "featuredImage", "pic", "photo_path",
               "image_path", "imagePath", "photoPath", "avatar_url", "avatarUrl", "profile_picture")
_DESIG_KEYS = ("designation", "position", "rank", "job_title", "jobTitle", "role", "post",
               "designation_name", "designationName")
_EMAIL_KEYS = ("email", "email_address", "emailAddress", "mail")
_DEPT_KEYS = ("department", "dept", "department_name", "departmentName", "dept_name", "deptName")
_LINK_KEYS = ("profile_url", "profileUrl", "url", "link", "permalink", "href")


def _json_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("en", "name", "title", "rendered", "value", "label"):
            if isinstance(value.get(key), str):
                return value[key]
    return ""


def _json_image(value, depth: int = 0) -> str:
    if depth > 5 or value is None:
        return ""
    if isinstance(value, str):
        value = value.strip()
        looks_like_path = "/" in value or url_extension(value) in IMAGE_EXTENSIONS
        return value if looks_like_path and not value.startswith("data:") else ""
    if isinstance(value, dict):
        for key in ("url", "src", "source_url", "original", "full", "large", "path", "file", "href"):
            found = _json_image(value.get(key), depth + 1)
            if found:
                return found
        for key in ("data", "attributes", "asset", "formats", "sizes", "medium", "thumbnail"):
            found = _json_image(value.get(key), depth + 1)
            if found:
                return found
    if isinstance(value, list) and value:
        return _json_image(value[0], depth + 1)
    return ""


def _json_record(obj: dict, page_url: str) -> Optional[dict]:
    if "/schema/person/" in str(obj.get("@id", "")):  # WordPress/Yoast: the post's author
        return None
    name = ""
    for key in _NAME_KEYS:
        candidate = clean_name(_json_text(obj.get(key)))
        if candidate and looks_like_name(candidate, strict=(key == "title")):
            name = candidate
            break
    if not name:
        return None
    image = next((img for img in (_json_image(obj.get(k)) for k in _IMAGE_KEYS) if img), "")
    if "gravatar.com" in image:  # account avatars of site editors, not faculty photos
        return None
    designation = next((t for t in (_json_text(obj.get(k)) for k in _DESIG_KEYS) if t), "")
    if not image and not designation:
        return None
    record = _empty_record()
    photo = unwrap_image_proxy(absolute_url(image, page_url)) if image else ""
    link = next((t for t in (_json_text(obj.get(k)) for k in _LINK_KEYS) if t), "")
    link_url = absolute_url(link, page_url) if link and ("/" in link) else ""
    if link_url and url_extension(link_url) in IMAGE_EXTENSIONS:
        link_url = ""
    record.update(
        name=name,
        designation=normalize_designation(designation),
        department_hint=clean_text(next((t for t in (_json_text(obj.get(k)) for k in _DEPT_KEYS) if t), "")),
        email=next((e for e in (extract_emails(_json_text(obj.get(k))) for k in _EMAIL_KEYS) if e), [""])[0],
        profile_url=link_url,
        photo_url="" if (not photo or is_placeholder_image(photo)) else photo,
    )
    return record


def _walk(obj, depth: int = 0):
    if depth > 30:
        return
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value, depth + 1)


def _flight_blobs(script_text: str) -> list:
    """Parse React Server Component payloads (Next.js App Router: self.__next_f.push)."""
    payload = []
    for match in re.finditer(r"self\.__next_f\.push\(\[\s*1\s*,\s*(\"(?:[^\"\\]|\\.)*\")\s*\]\)", script_text):
        try:
            payload.append(json.loads(match.group(1)))
        except ValueError:
            continue
    blobs = []
    for line in "".join(payload).splitlines():
        head, sep, body = line.partition(":")
        body = body if sep and re.fullmatch(r"[0-9a-fA-F]+", head) else line
        if body[:1] in ("{", "["):
            try:
                blobs.append(json.loads(body))
            except ValueError:
                continue
    return blobs


def extract_json_records(soup: BeautifulSoup, page_url: str) -> list[dict]:
    blobs = []
    flight_text = []
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        text = script.string or script.get_text() or ""
        if not text.strip():
            continue
        if script.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__") or script_type in ("application/json", "application/ld+json"):
            try:
                blobs.append(json.loads(text))
            except ValueError:
                pass
        elif "self.__next_f.push" in text:
            flight_text.append(text)
        else:
            for match in re.finditer(r"(?:__INITIAL_STATE__|__PRELOADED_STATE__|__APOLLO_STATE__|__DATA__|__NUXT__)\s*=\s*", text):
                try:
                    obj, _ = json.JSONDecoder().raw_decode(text[match.end():].lstrip())
                    blobs.append(obj)
                except ValueError:
                    pass
    if flight_text:
        blobs.extend(_flight_blobs("\n".join(flight_text)))
    for element in soup.find_all(attrs={"data-page": True}):  # Laravel Inertia.js
        try:
            blobs.append(json.loads(element["data-page"]))
        except ValueError:
            pass
    records = []
    for blob in blobs:
        for obj in _walk(blob):
            record = _json_record(obj, page_url)
            if record:
                records.append(record)
    return records


# ---------------------------------------------------------------------------------------
# Profile pages
# ---------------------------------------------------------------------------------------


def _name_tokens(name: str) -> set[str]:
    common = {"md", "mohammad", "muhammad", "mohammed", "mst", "dr", "prof", "engr", "abu", "abdul"}
    return {t for t in name_key(name).split() if len(t) >= 3 and t not in common}


def extract_profile(soup: BeautifulSoup, page_url: str, expected_name: str = "",
                    ignore_images: frozenset = frozenset()) -> dict:
    """Name, designation, best portrait etc. from a single faculty profile page."""
    record = _empty_record()
    main = soup.find("main") or soup.find("article") or soup.body or soup

    found_name = ""
    chrome = chrome_container_ids(soup)
    for level in ("h1", "h2", "h3"):
        for heading in soup.find_all(level):
            if in_containers(heading, chrome):
                continue
            for candidate in [heading.get_text(" ", strip=True)] + text_lines(heading.get_text("\n", strip=True))[:1]:
                if looks_like_name(candidate, strict=False):
                    found_name = clean_name(candidate)
                    break
            if found_name:
                break
        if found_name:
            break
    if not found_name:
        for candidate in (meta_content(soup, "og:title"), page_title(soup)):
            first = re.split(r"\s+[|\-–—]\s+", candidate or "")[0]
            if looks_like_name(first, strict=False):
                found_name = clean_name(first)
                break
    name = expected_name or found_name
    record["name"] = name

    person = _name_tokens(name or found_name)
    best_url, best_score = "", 0
    for index, (tag, url) in enumerate(collect_image_nodes(soup, page_url)):
        url = unwrap_image_proxy(url)
        if url in ignore_images or is_placeholder_image(url):
            continue
        score = 0
        alt_words = tokens((tag.get("alt") or "") + " " + (tag.get("title") or ""))
        url_words = tokens(urlsplit(url).path)
        overlap = len(person & alt_words)
        score += 4 + min(overlap - 1, 2) if overlap else 0
        score += 3 if person & url_words else 0
        score += 2 if _PHOTO_URL_HINT_RE.search(urlsplit(url).path) else 0
        ancestors = [a for _, a in zip(range(4), tag.parents)]
        if any(attr_tokens(a) & _PROFILE_CONTAINER_TOKENS for a in ancestors) or attr_tokens(tag) & _PROFILE_CONTAINER_TOKENS:
            score += 2
        if tag.find_parent(["main", "article"]) is not None:
            score += 1
        try:
            width, height = int(str(tag.get("width") or 0).rstrip("px")), int(str(tag.get("height") or 0).rstrip("px"))
        except ValueError:
            width = height = 0
        if max(width, height) >= 100:
            score += 1
        if width and height and 0.55 <= width / height <= 1.15:
            score += 1
        if index < 3:
            score += 1
        if score > best_score:
            best_url, best_score = url, score
    og_image = unwrap_image_proxy(absolute_url(meta_content(soup, "og:image", "twitter:image"), page_url))
    if og_image and og_image not in ignore_images and not is_placeholder_image(og_image) and not is_junk_url(og_image):
        og_score = 2 + (3 if person & tokens(urlsplit(og_image).path) else 0)
        if og_score > best_score:
            best_url, best_score = og_image, og_score
    record["photo_url"] = best_url if best_score >= 3 else ""

    lines = text_lines(main.get_text("\n", strip=True))[:150]
    start = 0
    for i, line in enumerate(lines):
        if name and name_key(line) == name_key(name):
            start = i
            break
    window = lines[start + 1:start + 10] + lines[:60]
    record["designation"], dept = _split_designation(_pick_designation(None, window, name))
    record["department_hint"] = dept or _department_hint(lines[:60])
    text = "\n".join(lines)
    record["email"] = _emails_in(main, text)
    record["phone"] = extract_phone(text)
    record["qualifications"] = extract_degrees(lines[:80], skip=(name, record["designation"]))
    record["research_interests"] = extract_research_interests(text)
    return record


def candidate_profile_links(soup: BeautifulSoup, page_url: str,
                            profile_res: Sequence[Pattern] = ()) -> list[tuple[str, str]]:
    """Links on a listing page that lead to individual faculty profiles."""
    page_key = canonical_url(page_url)
    found: list[tuple[str, str]] = []
    for url, text in page_links(soup, page_url):
        if canonical_url(url) == page_key or is_social_or_external_profile(url):
            continue
        if url_extension(url) in IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS:
            continue
        name_like = looks_like_name(clean_name(text), strict=False)
        if any(p.search(url) for p in profile_res) or (name_like and _PROFILE_PATH_HINT_RE.search(url)):
            found.append((url, clean_name(text) if name_like else ""))
    return found
