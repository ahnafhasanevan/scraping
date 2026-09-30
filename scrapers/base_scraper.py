"""Shared scraping engine. Each university module only provides configuration:
where to start, which URLs are faculty lists/profiles, and department names."""
from __future__ import annotations

import heapq
import itertools
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from utils.cleaner import clean_text, is_non_academic, name_key, slug_to_title
from utils.extractor import (
    candidate_profile_links,
    extract_cards,
    extract_json_records,
    extract_profile,
    extract_table_rows,
)
from utils.html_tools import (
    absolute_url,
    canonical_url,
    looks_js_rendered,
    meta_content,
    page_links,
    page_title,
    pagination_links,
    url_extension,
    IMAGE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
)
from utils.http_client import HttpClient, Page
from utils.models import FacultyRecord

# Link text of faculty lists: "Faculty Members", "Our Faculty", "Teaching Staff", "Faculty & Staff" ...
LISTING_TEXT_RE = re.compile(
    r"^(?:our\s+|all\s+|list\s+of\s+)?(?:full[-\s]?time\s+|part[-\s]?time\s+|adjunct\s+|permanent\s+)?"
    r"(?:faculty|faculties|teachers?|teaching\s+staff|academic\s+staff|people)"
    r"(?:\s+members?)?(?:\s*(?:&|and)\s*(?:staff|officers?))?(?:\s+(?:list|directory|profiles?))?$",
    re.I,
)
LISTING_URL_RE = re.compile(
    r"faculty[-_]?members?|faculties[-_](?:and[-_])?staff|faculty[-_](?:and[-_])?staff|teaching[-_]staff|"
    r"faculty[-_]list|faculties[-_]list|/faculty/?$|/faculty\.(?:php|html?)$|/faculties/?$|/teachers?/?$|"
    r"/people/?$|/our[-_]faculty",
    re.I,
)
FOLLOW_TEXT_RE = re.compile(
    r"\b(department|dept\.?|school\s+of|faculty\s+of|institute\s+of|academics?|departments|schools|faculties)\b", re.I)
FOLLOW_URL_RE = re.compile(r"department|dept|/school|faculty[-_]of|/faculty/|/academics?\b|/institute", re.I)
EXCLUDE_URL_RE = re.compile(
    r"news|event|notice|gallery|photo[-_]?album|video|admission|apply|result|login|signin|register|"
    r"calendar|tender|career|jobs?\b|alumni|/students?\b|club|publication|journal|conference|seminar|"
    r"workshop|convocation|scholarship|tuition|fees?\b|syllabus|download|/wp-admin|/wp-login|/feed|"
    r"/tag/|/category/|/author/|/print|/share|[?&]lang=|/bn/|/bn$|/search|/cart|/checkout|"
    r"/course-?details|/course/|/courses/|/research-?(?:project|grant|paper)|/blog",
    re.I,
)
UNWANTED_SUBDOMAINS = {
    "jobs", "career", "careers", "admission", "admissions", "library", "lib", "portal", "erp", "lms",
    "moodle", "elearning", "mail", "webmail", "result", "results", "alumni", "journal", "journals",
    "ojs", "conference", "shop", "store", "payment", "pay", "hostel", "transport", "exam", "online",
    "apply", "student", "students", "club", "clubs", "convocation", "newsletter", "blog", "dev",
    "test", "staging", "old", "beta", "api", "cdn", "static", "ums", "sis", "iums", "ucam", "oj",
}
STAFF_ONLY_RE = re.compile(r"(?:^|[/_-])(?:staffs?|officers?|officials?|employees)(?:[/_.-]|$)", re.I)
TEACHING_STAFF_RE = re.compile(r"teaching[-_]staff|facult(?:y|ies)[-_](?:and[-_])?staff", re.I)

_PAGE_DEPT_PATTERNS = [
    re.compile(r"Faculty\s+Members?\s+of\s+(?:the\s+)?(.+?)\s+Department", re.I),
    re.compile(r"Department\s+of\s+([A-Za-z][^|\-–—:,()]{1,70})", re.I),
    re.compile(r"Dept\.?\s+of\s+([A-Za-z][^|\-–—:,()]{1,70})", re.I),
    re.compile(r"\b([A-Z][A-Za-z&,\s]{1,60}?)\s+Department\b"),
    re.compile(r"School\s+of\s+([A-Za-z][^|\-–—:,()]{2,70})", re.I),
]
_SEGMENT_SUFFIX_RE = re.compile(
    r"(?:[-_](?:faculty|faculties|faculty[-_]members?|faculties[-_]staff|teaching[-_]staff|people|members?|"
    r"department|dept))+$|\.(?:php|html?|aspx?)$",
    re.I,
)
_GENERIC_SEGMENTS = {
    "people", "faculty", "faculties", "teachers", "teacher", "members", "member", "department", "dept",
    "departments", "home", "about", "academics", "academic", "en", "www", "index", "page", "pages",
    "site", "sites", "web", "main", "public", "school", "schools", "list", "all", "our-faculty",
}
COMMON_DEPARTMENTS = {
    "cse": "Computer Science and Engineering", "eee": "Electrical and Electronic Engineering",
    "ece": "Electronics and Communications Engineering", "ete": "Electronics and Telecommunication Engineering",
    "ice": "Information and Communication Engineering", "ict": "Information and Communication Technology",
    "ce": "Civil Engineering", "civil": "Civil Engineering", "me": "Mechanical Engineering",
    "ipe": "Industrial and Production Engineering", "te": "Textile Engineering", "textile": "Textile Engineering",
    "bba": "Business Administration", "ba": "Business Administration", "mba": "MBA Program",
    "english": "English", "law": "Law", "economics": "Economics", "pharmacy": "Pharmacy",
    "architecture": "Architecture", "arch": "Architecture", "math": "Mathematics", "mathematics": "Mathematics",
    "physics": "Physics", "chemistry": "Chemistry", "bangla": "Bangla", "ged": "General Education",
    "thm": "Tourism and Hospitality Management", "msj": "Media Studies and Journalism",
}


_NOT_FOUND_RE = re.compile(
    r"\b404\b|page\s+not\s+found|not\s+found|does\s*n[o']t\s+exist|no\s+longer\s+available|nothing\s+found", re.I)


def _looks_not_found(soup: Optional[BeautifulSoup]) -> bool:
    """'Soft 404': an error page served with status 200."""
    if soup is None:
        return True
    heading = soup.find("h1")
    texts = [page_title(soup), heading.get_text(" ", strip=True) if heading else ""]
    return any(len(t) < 120 and _NOT_FOUND_RE.search(t) for t in texts if t)


@dataclass
class ScrapeSettings:
    discovery_depth: int = 2
    max_pages: int = 350
    max_pagination: int = 40
    max_profiles: int = 700
    visit_profiles: str = "auto"      # auto | always | never
    render: str = "auto"              # auto | always | never
    skip_non_academic: bool = True
    deep: bool = False


class BaseScraper:
    # ---- configuration provided by each university module -----------------------------
    key = ""
    short_name = ""
    name = ""
    homepage = ""
    allowed_domains: tuple = ()        # registered domains; their subdomains are allowed too
    blocked_hosts: tuple = ()          # old/dev copies of the website
    start_urls: tuple = ()             # where link discovery begins
    seed_listing_urls: tuple = ()      # known faculty list pages (verified or likely)
    fallback_start_urls: tuple = ()    # only used if nothing was found
    listing_patterns: tuple = ()       # regexes for faculty list pages
    follow_patterns: tuple = ()        # regexes for pages worth exploring (departments, schools)
    profile_patterns: tuple = ()       # regexes for individual profile pages
    exclude_patterns: tuple = ()       # regexes for pages to never fetch
    department_names: dict = {}        # URL slug / subdomain -> department name
    id_profile_template = ""           # --deep: profile URL with an {id} placeholder
    id_range = (1, 400)
    render_mode = ""                   # override the global render mode for this site

    def __init__(self, client: HttpClient, settings: Optional[ScrapeSettings] = None, log: Optional[logging.Logger] = None):
        self.client = client
        self.settings = settings or ScrapeSettings()
        self.log = log or logging.getLogger(f"scraper.{self.key}")
        self._listing_res = [re.compile(p, re.I) for p in self.listing_patterns]
        self._follow_res = [re.compile(p, re.I) for p in self.follow_patterns]
        self._profile_res = [re.compile(p, re.I) for p in self.profile_patterns]
        self._exclude_res = [re.compile(p, re.I) for p in self.exclude_patterns]
        self.records: list[FacultyRecord] = []
        self._by_profile: dict[str, FacultyRecord] = {}
        self._by_person: dict[tuple, FacultyRecord] = {}
        self._by_photo: dict[tuple, FacultyRecord] = {}
        self._orphan_links: dict[str, tuple[str, str, str]] = {}
        self._ignore_images: set[str] = set()
        self.pages_fetched = 0
        self.listing_pages: list[str] = []

    # ================================================================== entry point
    def run(self) -> list[FacultyRecord]:
        self.log.info("%s: discovering faculty pages ...", self.short_name)
        self._crawl(list(self.start_urls), list(self.seed_listing_urls))
        if not self.records and self.fallback_start_urls:
            self.log.info("%s: nothing found yet, trying fallback start pages", self.short_name)
            self._crawl(list(self.fallback_start_urls), [])
        if self.settings.visit_profiles != "never":
            self._visit_profiles()
        if self.settings.deep and self.id_profile_template:
            self._enumerate_profile_ids()
        with_photo = sum(1 for r in self.records if r.photo_url)
        self.log.info(
            "%s: %d faculty members found (%d with a photo) from %d list pages, %d pages fetched",
            self.short_name, len(self.records), with_photo, len(self.listing_pages), self.pages_fetched,
        )
        return self.records

    # ================================================================== URL rules
    def is_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host or not any(host == d or host.endswith("." + d) for d in self.allowed_domains):
            return False
        if host in self.blocked_hosts or host.split(".")[0] in UNWANTED_SUBDOMAINS:
            return False
        if url_extension(url) in IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS:
            return False
        if any(p.search(url) for p in self._exclude_res):
            return False
        return True

    def is_listing_url(self, url: str) -> bool:
        if any(p.search(url) for p in self._listing_res):
            return True
        return bool(LISTING_URL_RE.search(urlsplit(url).path)) and not self.is_profile_url(url)

    def is_profile_url(self, url: str) -> bool:
        return any(p.search(url) for p in self._profile_res)

    def _worth_following(self, url: str, text: str) -> bool:
        path = urlsplit(url).path + "?" + urlsplit(url).query
        if EXCLUDE_URL_RE.search(path):
            return False
        if any(p.search(url) for p in self._follow_res):
            return True
        return bool(FOLLOW_URL_RE.search(path) or FOLLOW_TEXT_RE.search(text or ""))

    def _is_staff_only(self, url: str) -> bool:
        path = urlsplit(url).path
        return bool(STAFF_ONLY_RE.search(path)) and not TEACHING_STAFF_RE.search(path)

    # ================================================================== fetching
    def fetch(self, url: str) -> tuple[Optional[Page], Optional[BeautifulSoup]]:
        mode = self.render_mode or self.settings.render
        page = None
        if mode == "always":
            page = self.client.get_page(url, render=True)
        if page is None:
            page = self.client.get_page(url)
        self.pages_fetched += 1
        if page is None:
            return None, None
        soup = BeautifulSoup(page.html, "lxml")
        if mode == "auto" and not page.rendered and looks_js_rendered(soup) and self.client.can_render:
            rendered = self.client.get_page(url, render=True)
            if rendered is not None:
                page, soup = rendered, BeautifulSoup(rendered.html, "lxml")
        return page, soup

    # ================================================================== crawling
    def _crawl(self, start_urls: list[str], seed_urls: list[str]) -> None:
        counter = itertools.count()
        queue: list = []

        def push(priority: int, url: str, depth: int, kind: str, via: str = "", dept: str = "") -> None:
            heapq.heappush(queue, (priority, depth, next(counter), url, kind, via, dept))

        for url in seed_urls:
            push(0, url, 0, "listing")
        for url in start_urls:
            push(1, url, 0, "explore")
        visited: set[str] = set()
        max_depth = max(0, self.settings.discovery_depth)
        while queue and self.pages_fetched < self.settings.max_pages:
            _, depth, _, url, kind, via, inherited_dept = heapq.heappop(queue)
            key = canonical_url(url)
            if key in visited or not self.is_allowed(url):
                continue
            visited.add(key)
            page, soup = self.fetch(url)
            if page is None or _looks_not_found(soup):
                continue
            visited.add(canonical_url(page.url))
            if kind == "listing" and canonical_url(page.url) != key and not self.is_listing_url(page.url):
                kind = "explore"  # a guessed list URL redirected somewhere else (e.g. the home page)
            if not self._ignore_images:
                home_image = absolute_url(meta_content(soup, "og:image", "twitter:image"), page.url)
                if home_image:
                    self._ignore_images.add(home_image)

            is_listing = kind == "listing" or self.is_listing_url(page.url)
            if not is_listing:
                strict_cards = extract_cards(soup, page.url, lenient=False, profile_res=self._profile_res)
                is_listing = sum(1 for c in strict_cards if c["designation"]) >= 3
            if is_listing and not self._is_staff_only(page.url):
                dept = inherited_dept or self.department_for(page.url, soup, via)
                found = self._parse_listing(page, soup, dept)
                if not found and not page.rendered and self.client.can_render and (self.render_mode or self.settings.render) != "never":
                    rendered = self.client.get_page(page.url, render=True)
                    if rendered is not None:
                        page, soup = rendered, BeautifulSoup(rendered.html, "lxml")
                        found = self._parse_listing(page, soup, dept)
                if found:
                    self.listing_pages.append(page.url)
                for next_url in pagination_links(soup, page.url)[: self.settings.max_pagination]:
                    push(0, next_url, depth, "listing", via, dept)

            if depth > max_depth:
                continue
            for link, text in page_links(soup, page.url):
                if canonical_url(link) in visited or not self.is_allowed(link) or self.is_profile_url(link):
                    continue
                if self._is_staff_only(link):
                    continue
                if self.is_listing_url(link) or LISTING_TEXT_RE.match(text or ""):
                    push(0, link, depth + 1, "listing", text)
                elif depth < max_depth and self._worth_following(link, text):
                    push(1, link, depth + 1, "explore", text)

    def _parse_listing(self, page: Page, soup: BeautifulSoup, department: str) -> int:
        raw_records = extract_cards(soup, page.url, lenient=True, profile_res=self._profile_res)
        raw_records += extract_table_rows(soup, page.url)
        raw_records += extract_json_records(soup, page.url)
        added = 0
        for raw in raw_records:
            if self._add_record(raw, department, page.url):
                added += 1
        for url, text in candidate_profile_links(soup, page.url, self._profile_res):
            if self.is_allowed(url):
                key = canonical_url(url)
                if key not in self._by_profile and key not in self._orphan_links:
                    self._orphan_links[key] = (url, text, department)
        if raw_records or self._orphan_links:
            self.log.debug("%s: %d people on %s [%s]", self.short_name, len(raw_records), page.url, department)
        return len(raw_records)

    # ================================================================== records
    def _add_record(self, raw: dict, department: str, source_page: str) -> Optional[FacultyRecord]:
        name = clean_text(raw.get("name"))
        if not name:
            return None
        if self.settings.skip_non_academic and is_non_academic(raw.get("designation", "")):
            return None
        dept = department
        hint = self.normalize_department(raw.get("department_hint", ""))
        if hint and (not dept or dept == "Other"):
            dept = hint
        dept = dept or "Other"
        person = name_key(name)
        profile_key = canonical_url(raw["profile_url"]) if raw.get("profile_url") else ""
        photo_key = (person, urlsplit(raw["photo_url"]).path.lower()) if raw.get("photo_url") else None

        existing = None
        if profile_key and profile_key in self._by_profile:
            existing = self._by_profile[profile_key]
        elif (person, dept.lower()) in self._by_person:
            existing = self._by_person[(person, dept.lower())]
        elif photo_key and photo_key in self._by_photo:
            existing = self._by_photo[photo_key]
        if existing is not None:
            existing.fill_missing(raw)
            record = existing
        else:
            record = FacultyRecord(
                university=self.short_name, university_name=self.name, department=dept, name=name,
                designation=raw.get("designation", ""), qualifications=raw.get("qualifications", ""),
                email=raw.get("email", ""), phone=raw.get("phone", ""),
                research_interests=raw.get("research_interests", ""), profile_url=raw.get("profile_url", ""),
                photo_url=raw.get("photo_url", ""), source_page=source_page,
            )
            self.records.append(record)
        self._by_person[(person, record.department.lower())] = record
        if record.profile_url:
            self._by_profile[canonical_url(record.profile_url)] = record
        if record.photo_url:
            self._by_photo[(person, urlsplit(record.photo_url).path.lower())] = record
        return record

    # ================================================================== departments
    def department_for(self, url: str, soup: Optional[BeautifulSoup] = None, via_text: str = "") -> str:
        mapped = self._mapped_department(url)
        if mapped:
            return mapped
        sources = []
        if soup is not None:
            for crumb in soup.find_all(class_=re.compile(r"breadcrumb", re.I))[:1]:
                sources.append(crumb.get_text(" ", strip=True))
            sources.append(page_title(soup))
            sources.append(meta_content(soup, "og:title"))
            for heading in soup.find_all(["h1", "h2"])[:4]:
                sources.append(heading.get_text(" ", strip=True))
        sources.append(via_text)
        own = {self.key.lower(), self.short_name.lower(), self.name.lower()}
        for text in sources:
            for pattern in _PAGE_DEPT_PATTERNS:
                match = pattern.search(text or "")
                if match:
                    dept = self.normalize_department(match.group(1))
                    if dept and dept.lower() not in own | {"faculty members", "faculty", "the", "our", "welcome to the"}:
                        return dept
        return self._department_from_slug(url) or "Other"

    def _mapped_department(self, url: str) -> str:
        if not self.department_names:
            return ""
        parts = urlsplit(url)
        candidates = []
        for segment in parts.path.split("/"):
            segment = segment.lower()
            if segment:
                candidates += [segment, _SEGMENT_SUFFIX_RE.sub("", segment), re.sub(r"^department[-_]of[-_]", "", segment)]
        candidates.append((parts.hostname or "").split(".")[0].lower())
        for candidate in candidates:
            if candidate in self.department_names:
                return self.department_names[candidate]
        return ""

    def _department_from_slug(self, url: str) -> str:
        parts = urlsplit(url)
        own = {self.key.lower(), self.short_name.lower()}
        segments = [s for s in parts.path.split("/") if s and s.lower() not in own]
        for i, segment in enumerate(segments):
            if LISTING_URL_RE.search("/" + segment) and i > 0:
                previous = _SEGMENT_SUFFIX_RE.sub("", segments[i - 1]).lower()
                if previous and previous not in _GENERIC_SEGMENTS:
                    return self.normalize_department(slug_to_title(previous))
            stripped = _SEGMENT_SUFFIX_RE.sub("", segment)
            if stripped != segment and stripped and stripped.lower() not in _GENERIC_SEGMENTS | own:
                return self.normalize_department(slug_to_title(stripped))
        label = (parts.hostname or "").split(".")[0].lower()
        if label and label not in _GENERIC_SEGMENTS | own and len(label) <= 12:
            return self.normalize_department(label)
        return ""

    def normalize_department(self, value: str) -> str:
        value = clean_text(value)
        value = re.sub(r"^(?:the\s+)?(?:department|dept\.?)\s+of\s+", "", value, flags=re.I)
        value = re.sub(r"\s*(?:faculty\s+members?|faculties\s*&\s*staff|teaching\s+staff)\s*$", "", value, flags=re.I)
        value = value.strip(" ,.-|:")
        if not value or len(value) > 70:
            return ""
        lookup = value.lower()
        if lookup in self.department_names:
            return self.department_names[lookup]
        if lookup in COMMON_DEPARTMENTS:
            return COMMON_DEPARTMENTS[lookup]
        if value.isupper() and len(value) > 5:
            value = value.title()
        return value.replace(" & ", " and ")

    # ================================================================== profiles
    def _visit_profiles(self) -> None:
        mode = self.settings.visit_profiles
        jobs: list[tuple[str, Optional[FacultyRecord], str, str]] = []
        for record in self.records:
            if record.profile_url and (mode == "always" or not record.photo_url):
                jobs.append((record.profile_url, record, "", record.department))
        for key, (url, text, dept) in self._orphan_links.items():
            if key not in self._by_profile:
                jobs.append((url, None, text, dept))
        jobs = jobs[: self.settings.max_profiles]
        if jobs:
            self.log.info("%s: visiting %d profile pages ...", self.short_name, len(jobs))
        for url, record, link_text, dept in jobs:
            if record is None and canonical_url(url) in self._by_profile:
                record = self._by_profile[canonical_url(url)]
                if record.photo_url and mode != "always":
                    continue
            page, soup = self.fetch(url)
            if not self._is_real_profile(page, soup):
                continue
            data = extract_profile(soup, page.url, expected_name=record.name if record else link_text,
                                   ignore_images=frozenset(self._ignore_images))
            data["profile_url"] = url
            if record is None:
                if data["name"] and (data["photo_url"] or data["designation"]):
                    self._add_record(data, dept or self.department_for(page.url, soup), page.url)
                continue
            if data["photo_url"] and (mode == "always" or not record.photo_url):
                record.photo_url = data["photo_url"]
            hint = self.normalize_department(data.get("department_hint", ""))
            if hint and record.department == "Other":
                record.department = hint
            data.pop("name", None)
            record.fill_missing(data)

    @staticmethod
    def _is_real_profile(page: Optional[Page], soup: Optional[BeautifulSoup]) -> bool:
        """Not an error page and not a redirect to the home page."""
        if page is None or _looks_not_found(soup):
            return False
        parts = urlsplit(page.url)
        return bool(parts.query) or parts.path.strip("/") not in ("", "index.php", "index.html", "home")

    def _enumerate_profile_ids(self) -> None:
        start, stop = self.id_range
        misses = 0
        self.log.info("%s: --deep: checking profile ids %d-%d ...", self.short_name, start, stop)
        for number in range(start, stop):
            url = self.id_profile_template.format(id=number)
            if canonical_url(url) in self._by_profile:
                misses = 0
                continue
            page, soup = self.fetch(url)
            real = self._is_real_profile(page, soup)
            data = extract_profile(soup, page.url, ignore_images=frozenset(self._ignore_images)) if real else None
            if data and data["name"] and (data["photo_url"] or data["designation"]):
                data["profile_url"] = url
                self._add_record(data, self.normalize_department(data.get("department_hint", "")) or "Other", url)
                misses = 0
            else:
                misses += 1
                if misses >= 30:
                    break
