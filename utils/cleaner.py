"""Normalisation helpers for names, designations, contact details and file names."""
from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)

# ---------------------------------------------------------------------------------------
# Generic text
# ---------------------------------------------------------------------------------------


def clean_text(value: str | None) -> str:
    """Collapse whitespace, drop zero-width characters and trim."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", str(value)).translate(_ZERO_WIDTH)
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def text_lines(value: str) -> list[str]:
    """Split multi-line text into cleaned, non-empty, de-duplicated lines."""
    lines: list[str] = []
    for raw in re.split(r"[\r\n]+", value or ""):
        line = clean_text(raw).strip(" |:-–—•*")
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return lines


# ---------------------------------------------------------------------------------------
# Designations
# ---------------------------------------------------------------------------------------

ACADEMIC_RE = re.compile(
    r"\bprof\.|\b(?:asst|assoc|sr)\.?\s*prof\b|\b(professor|lecturer|instructor|teacher|dean|chair(?:man|person|woman)?|"
    r"head\s+of|head\b|director|co-?ordinator|adjunct|emeritus|visiting|faculty\s+member|tutor|"
    r"teaching\s+assistant|research\s+(?:assistant|associate|fellow|professor)|"
    r"(?:pro[\s-]*)?vice[\s-]*chancellor|treasurer|advis[oe]r|demonstrator|on\s+(?:study\s+)?leave)\b",
    re.I,
)
# Words that only teaching staff carry (used to keep e.g. "Lecturer & Coordinator").
STRONG_ACADEMIC_RE = re.compile(
    r"\bprof\.|\b(?:asst|assoc|sr)\.?\s*prof\b|\b(professor|lecturer|instructor|teacher|dean|chair(?:man|person|woman)?|"
    r"head\s+of\s+(?:the\s+)?(?:department|dept)|adjunct|emeritus|visiting|tutor|"
    r"(?:pro[\s-]*)?vice[\s-]*chancellor)\b",
    re.I,
)
NON_ACADEMIC_RE = re.compile(
    r"\b(officer|registrar|technician|technical\s+assistant|lab(?:oratory)?\s+(?:assistant|attendant|"
    r"in[\s-]*charge|instructor)|clerk|peon|driver|accountant|cashier|executive|librarian|"
    r"office\s+(?:assistant|secretary)|computer\s+operator|programmer|receptionist|store\s*keeper|"
    r"messenger|guard|cleaner|mlss|staff)\b",
    re.I,
)

_DESIGNATION_ABBREVIATIONS = [
    (r"\bAsst\.?(?=\s)", "Assistant"),
    (r"\bAssoc\.?(?=\s)", "Associate"),
    (r"\bProf\.(?=\s|$)", "Professor"),
    (r"\bSr\.?(?=\s)", "Senior"),
    (r"\bJr\.?(?=\s)", "Junior"),
    (r"\bLect\.?(?=\s|$)", "Lecturer"),
    (r"\bDept\.?(?=\s)", "Department"),
    (r"\s*&amp;\s*", " & "),
]


def normalize_designation(value: str | None) -> str:
    """'Asst. Prof. & Head' -> 'Assistant Professor & Head' (other text is kept)."""
    value = clean_text(value)
    if not value:
        return ""
    value = re.sub(r"^(designation|position|title)\s*[:\-]\s*", "", value, flags=re.I)
    value = re.sub(r"\bAsst\.?\s*Prof\.?", "Assistant Professor", value, flags=re.I)
    value = re.sub(r"\bAssoc\.?\s*Prof\.?", "Associate Professor", value, flags=re.I)
    for pattern, replacement in _DESIGNATION_ABBREVIATIONS:
        value = re.sub(pattern, replacement, value, flags=re.I)
    if value.isupper():
        value = value.title()
    return clean_text(value).strip(" ,;|-")


def looks_like_designation(value: str) -> bool:
    value = clean_text(value)
    return bool(value) and len(value) <= 140 and bool(ACADEMIC_RE.search(value) or NON_ACADEMIC_RE.search(value))


def is_non_academic(designation: str) -> bool:
    """True for officers/lab staff etc. (but not for 'Lecturer & Lab Coordinator')."""
    designation = clean_text(designation)
    if not designation:
        return False
    return bool(NON_ACADEMIC_RE.search(designation)) and not STRONG_ACADEMIC_RE.search(designation)


# ---------------------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------------------

_HONORIFIC_RE = re.compile(
    r"^(?:(?:prof(?:essor)?|dr|engr|mr|mrs|ms|miss|mst|md|mohd)\.?\s+|(?:prof|dr|engr|md)\.)+",
    re.I,
)
_DEGREE_SUFFIX_RE = re.compile(
    r"(?:,\s*|\s+)(?:ph\.?\s?d|d\.?\s?phil|m\.?\s?phil|pe(?:ng)?|fcma|fca|acma|aca|cfa|mba|m\.?\s?sc|jr|sr)\.?\s*$",
    re.I,
)
_NAME_STOPWORDS = {
    "admin", "administrator", "webmaster", "editor", "author", "guest", "anonymous",
    "about", "academic", "academics", "admission", "admissions", "all", "alumni", "and", "apply",
    "are", "at", "biography", "by", "campus", "career", "chairman's", "click", "contact",
    "copyright", "course", "courses", "curriculum", "cv", "dean's", "department", "departments",
    "details", "detail", "download", "education", "email", "e-mail", "event", "events",
    "experience", "ext", "faculties", "faculty", "for", "from", "gallery", "history", "home",
    "image", "in", "interest", "interests", "is", "journal", "leave", "library", "list", "login",
    "mail", "members", "member", "menu", "message", "mission", "mobile", "more", "news",
    "notice", "of", "office", "officers", "on", "our", "overview", "people", "phone", "photo",
    "profile", "program", "programme", "programs", "publication", "publications", "read",
    "research", "resume", "room", "school", "search", "see", "show", "staff", "teacher",
    "teachers", "team", "tel", "the", "to", "university", "view", "vision", "we", "welcome",
    "with", "your",
}
_NAME_CHARS_RE = re.compile(r"^[^\W\d_](?:[^\W\d_]|[\s.'’`,-])*$")


def strip_honorifics(name: str) -> str:
    return _HONORIFIC_RE.sub("", clean_text(name)).strip()


def clean_name(value: str | None) -> str:
    """Tidy a scraped name: drop labels, numbering, bracketed notes and trailing designations."""
    name = clean_text(value)
    if not name:
        return ""
    name = re.sub(r"^(name|faculty|teacher)\s*[:\-]\s*", "", name, flags=re.I)
    name = re.sub(r"^\(?\d{1,3}[.)]\s+", "", name)                      # "1. " / "12) "
    name = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*", " ", name)              # "(On Leave)"
    # "Dr. X, Professor" / "Dr. X - Lecturer" -> "Dr. X"
    parts = re.split(r"\s*(?:,|\s[-–—|]\s)\s*", name)
    if len(parts) > 1 and any(looks_like_designation(p) for p in parts[1:]):
        name = parts[0]
    return clean_text(name).strip(" ,;:-|")


def looks_like_name(value: str | None, strict: bool = True) -> bool:
    """Heuristic check that a string is a person's name (not a heading, label or sentence)."""
    name = clean_name(value)
    if not (3 <= len(name) <= 70):
        return False
    core = _DEGREE_SUFFIX_RE.sub("", strip_honorifics(name)).strip(" ,.")
    core = _DEGREE_SUFFIX_RE.sub("", core).strip(" ,.")
    if not core or not _NAME_CHARS_RE.match(core):
        return False
    words = [w for w in re.split(r"[\s,]+", core) if w]
    if not words or len(words) > 7:
        return False
    has_honorific = bool(_HONORIFIC_RE.match(name))
    if len(words) == 1 and (len(core) < 3 or (strict and not has_honorific)):
        return False
    lowered = {w.lower().strip(".'") for w in words}
    if lowered & _NAME_STOPWORDS:
        return False
    with_punctuation = strip_honorifics(name)
    if any(p.search(text) for p in (ACADEMIC_RE, NON_ACADEMIC_RE) for text in (core, with_punctuation)):
        return False
    capitalised = sum(1 for w in words if w[0].isupper())
    return capitalised >= max(1, (len(words) + 1) // 2)


def name_key(name: str) -> str:
    """Comparison key: 'Prof. Dr. Md. Rahman, PhD' and 'Md Rahman' share the same key."""
    core = _DEGREE_SUFFIX_RE.sub("", strip_honorifics(clean_name(name)))
    core = unicodedata.normalize("NFKD", core).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]+", " ", core.lower()).strip()


# ---------------------------------------------------------------------------------------
# Contact details, degrees, research interests
# ---------------------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_AT_RE = re.compile(r"\s*[\[\(\{<]\s*(?:at|@)\s*[\]\)\}>]\s*", re.I)
_DOT_RE = re.compile(r"\s*[\[\(\{<]\s*dot\s*[\]\)\}>]\s*", re.I)
_PHONE_LABEL_RE = re.compile(
    r"(?:phone|tel(?:ephone)?|mobile|cell|contact(?:\s+no)?|ext(?:ension)?)\.?\s*(?:no\.?)?\s*[:\-]?\s*"
    r"(\+?[\d][\d\s\-()/,]{2,24}\d)",
    re.I,
)
_BD_MOBILE_RE = re.compile(r"(?:\+?88)?01[3-9]\d{2}[-\s]?\d{6}")
DEGREE_RE = re.compile(
    r"(?:\bPh\.?\s?D\b|\bD\.?\s?Phil\b|\bM\.?\s?Phil\b|\bM\.?\s?Sc\b|\bB\.?\s?Sc\b|\bMBA\b|\bBBA\b|"
    r"\bEMBA\b|\bLL\.?\s?M\b|\bLL\.?\s?B\b|\bM\.?\s?Eng\b|\bB\.?\s?Eng\b|\bM\.?\s?Pharm\b|"
    r"\bB\.?\s?Pharm\b|\bM\.?\s?Arch\b|\bB\.?\s?Arch\b|\bMSS\b|\bBSS\b|\bMPH\b|\bMBBS\b|"
    r"\bM\.\s?A\.|\bB\.\s?A\.|\bM\.\s?S\.|\bB\.\s?S\.|\bMS\s+(?:in|from)\b|\bPost[-\s]?Doc)",
)
_RESEARCH_RE = re.compile(r"research\s+(?:interests?|areas?)\s*[:\-]\s*(.+)", re.I)


def deobfuscate_email_text(text: str) -> str:
    return _DOT_RE.sub(".", _AT_RE.sub("@", text or ""))


def extract_emails(text: str) -> list[str]:
    found: list[str] = []
    for match in EMAIL_RE.findall(deobfuscate_email_text(text)):
        email = match.strip(".").lower()
        if email not in found and not email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            found.append(email)
    return found


def extract_phone(text: str) -> str:
    text = text or ""
    match = _PHONE_LABEL_RE.search(text)
    if match:
        return clean_text(match.group(1)).strip(" ,/-")
    match = _BD_MOBILE_RE.search(text)
    return match.group(0) if match else ""


def extract_degrees(lines: list[str], skip: tuple[str, ...] = ()) -> str:
    degrees = [
        line for line in lines
        if len(line) <= 220 and line not in skip and DEGREE_RE.search(line) and "@" not in line
    ]
    return "; ".join(dict.fromkeys(degrees))[:600]


def extract_research_interests(text: str) -> str:
    match = _RESEARCH_RE.search(text or "")
    return clean_text(match.group(1))[:400] if match else ""


# ---------------------------------------------------------------------------------------
# File names (Windows safe)
# ---------------------------------------------------------------------------------------

_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(value: str, max_len: int = 80, default: str = "unnamed") -> str:
    """Make a string safe to use as a Windows/macOS/Linux file or folder name."""
    name = unicodedata.normalize("NFKC", value or "")
    name = _INVALID_FS_CHARS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".").strip()
    if not name:
        name = default
    if name.split(".")[0].upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name


def slug_to_title(slug: str) -> str:
    """'department-of-computer-science-and-engineering' -> 'Computer Science and Engineering'."""
    words = re.split(r"[-_\s]+", slug.strip("/ "))
    words = [w for w in words if w]
    if words[:2] and [w.lower() for w in words[:2]] == ["department", "of"]:
        words = words[2:]
    small = {"and", "of", "in", "for", "the", "&"}
    titled = [w.lower() if (i and w.lower() in small) else (w.upper() if len(w) <= 3 and w.lower() not in small else w.capitalize()) for i, w in enumerate(words)]
    return " ".join(titled)
