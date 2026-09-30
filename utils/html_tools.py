"""Low-level HTML helpers: image URLs, junk filtering, links, pagination, JS detection."""
from __future__ import annotations

import re
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".jfif", ".tif", ".tiff")
DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".mp4", ".mp3")

# Attributes used by lazy-loading libraries, best (full size) first.
_FULL_SIZE_ATTRS = ("data-full", "data-large", "data-large_image", "data-orig-file", "data-zoom-image", "data-hi-res")
_LAZY_ATTRS = (
    "data-src", "data-lazy-src", "data-original", "data-lazy", "data-url", "data-img", "data-image",
    "data-pagespeed-lazy-src", "data-echo", "data-unveil", "data-medium-file", "data-thumb",
)
_SRCSET_ATTRS = ("data-srcset", "data-lazy-srcset", "srcset")
_BG_ATTRS = ("data-bg", "data-background", "data-background-image", "data-bg-src", "data-image-src")
_BG_STYLE_RE = re.compile(r"background(?:-image)?\s*:[^;]*?url\(\s*['\"]?([^'\")]+?)['\"]?\s*\)", re.I)
_SRCSET_ITEM_RE = re.compile(r"\s*([^\s,][^\s]*?)(?:\s+(\d+(?:\.\d+)?)([wx]))?\s*(?:,|$)")

_PLACEHOLDER_SRC_RE = re.compile(
    r"(^data:|blank\.(gif|png)|spacer\.gif|transparent\.(gif|png)|lazy[-_]?(load|placeholder)?\.(gif|png|svg)|"
    r"placeholder\.(gif|png|svg|jpg)|loading\.(gif|svg)|1x1\.(gif|png)|pixel\.(gif|png))",
    re.I,
)
# Images whose URL/alt/class contains one of these words are decoration, not portraits.
JUNK_TOKENS = {
    "logo", "logos", "icon", "icons", "favicon", "banner", "banners", "slider", "sliders", "slide",
    "slides", "sprite", "sprites", "bg", "background", "backgrounds", "pattern", "shape", "shapes",
    "arrow", "arrows", "loader", "loading", "spinner", "facebook", "twitter", "linkedin", "youtube",
    "instagram", "whatsapp", "social", "flag", "flags", "qr", "qrcode", "captcha", "btn", "badge",
    "advertisement", "ads", "sponsor", "sponsors", "partner", "partners", "news", "event",
    "events", "notice", "notices", "campus", "building", "hero", "overlay", "decor", "dots",
    "signature", "seal", "stamp", "certificate", "poster", "flyer", "brochure", "convocation",
    "seminar", "workshop", "conference", "scholarship", "watermark", "ribbon", "emoji", "infographic",
}
PLACEHOLDER_TOKENS = {
    "placeholder", "noimage", "no-image", "no_image", "nophoto", "no-photo", "no_photo", "dummy",
    "default-avatar", "default-user", "default-profile", "blank-profile", "avatar-default",
    "user-default", "profile-default", "no-avatar", "noavatar", "image-not-found", "not-found",
}
# Generic file names that are placeholders when they are not inside a per-person folder.
PLACEHOLDER_FILENAMES = {
    "default", "avatar", "user", "users", "no-image", "noimage", "placeholder", "dummy", "blank",
    "male", "female", "man", "woman", "person", "default-avatar", "user-avatar", "default-user",
    "demo", "sample",
}
# Class/id words of navigation areas. Deliberately narrow: words such as "nav", "header"
# or "social" also appear on real faculty cards ("nav-faculty" tabs, "card-header", ...).
_CHROME_TOKENS = {
    "navbar", "navigation", "menu", "menus", "megamenu", "mainmenu", "footer", "topbar",
    "breadcrumb", "breadcrumbs", "cookie", "cookies", "copyright",
}
_SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "twitter.com", "x.com", "linkedin.com", "youtube.com", "instagram.com",
    "researchgate.net", "scholar.google", "orcid.org", "wa.me", "whatsapp.com", "t.me", "github.com",
    "google.com", "goo.gl", "bit.ly", "academia.edu", "scopus.com", "publons.com", "web.of.science",
)
_PAGE_PARAMS = {"page", "p", "pg", "paged", "pageno", "page_no", "pagenum", "start", "offset", "per_page"}
_NEXT_TEXTS = {"next", "next page", "next »", "next ›", "next >", "»", "›", ">", ">>", "›»", "older"}


def tokens(value: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (value or "").lower()) if t}


def attr_tokens(tag: Tag) -> set[str]:
    classes = tag.get("class") or []
    if isinstance(classes, str):
        classes = [classes]
    found: set[str] = set()
    for value in list(classes) + [tag.get("id") or ""]:
        found |= tokens(value)
    return found


def absolute_url(href: Optional[str], base: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:", "#", "about:")):
        return ""
    href = href.replace("\\", "/").replace(" ", "%20")
    url = urljoin(base, href)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return ""
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))


def canonical_url(url: str) -> str:
    """Key used to recognise the same page: no fragment, no 'www.', no trailing slash."""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return f"{host}{path}{'?' + query if query else ''}"


def url_extension(url: str) -> str:
    path = urlsplit(url).path.lower()
    match = re.search(r"\.[a-z0-9]{2,5}$", path)
    return match.group(0) if match else ""


# ---------------------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------------------


def best_from_srcset(value: str) -> str:
    best_url, best_size = "", -1.0
    for match in _SRCSET_ITEM_RE.finditer(value or ""):
        url, size, unit = match.group(1), match.group(2), match.group(3)
        if not url:
            continue
        score = float(size) * (1 if unit == "w" else 1000) if size else 0.0
        if score > best_size:
            best_url, best_size = url, score
    return best_url


def image_urls(tag: Tag, base_url: str) -> list[str]:
    """All usable image URLs of an <img>/element, best (largest, real) first."""
    raw: list[str] = []
    is_img = tag.name in ("img", "amp-img", "source")
    if is_img:
        for attr in _FULL_SIZE_ATTRS:
            raw.append(tag.get(attr) or "")
        for attr in _SRCSET_ATTRS:
            raw.append(best_from_srcset(tag.get(attr) or ""))
        if tag.parent is not None and tag.parent.name == "picture":
            for source in tag.parent.find_all("source"):
                raw.append(best_from_srcset(source.get("srcset") or source.get("data-srcset") or ""))
        for attr in _LAZY_ATTRS:
            raw.append(tag.get(attr) or "")
    for attr in _BG_ATTRS:
        raw.append(tag.get(attr) or "")
    if is_img:
        raw.append(tag.get("src") or "")
    style = tag.get("style") or ""
    match = _BG_STYLE_RE.search(style)
    if match:
        raw.append(match.group(1))
    urls: list[str] = []
    for value in raw:
        value = (value or "").strip()
        if not value or _PLACEHOLDER_SRC_RE.search(value):
            continue
        url = absolute_url(value, base_url)
        if url and url not in urls and url_extension(url) not in _NOT_IMAGE_EXTENSIONS:
            urls.append(url)
    return urls


_NOT_IMAGE_EXTENSIONS = (".svg", ".ico", ".js", ".css", ".html", ".htm") + DOCUMENT_EXTENSIONS


def is_placeholder_image(url: str) -> bool:
    path = urlsplit(url).path.lower()
    folder, _, filename = path.rpartition("/")
    stem = re.sub(r"\.[a-z0-9]{2,5}$", "", filename)
    stem = re.sub(r"[-_]?\d+x\d+$", "", stem)
    if stem in PLACEHOLDER_FILENAMES and not re.search(r"\d", folder):
        return True
    return any(token in path for token in PLACEHOLDER_TOKENS)


def is_junk_url(url: str) -> bool:
    """Decoration judged from the URL alone (logos, icons, theme assets, ...)."""
    path = urlsplit(url).path.lower()
    if url_extension(url) in (".svg", ".ico"):
        return True
    if "/themes/" in path or "/plugins/" in path or "/emoji" in path:
        return True
    return bool(tokens(path) & JUNK_TOKENS)


def is_junk_image(tag: Tag, url: str) -> bool:
    if is_junk_url(url):
        return True
    if (tokens(tag.get("alt") or "") | attr_tokens(tag)) & JUNK_TOKENS:
        return True
    width, height = _int_attr(tag, "width"), _int_attr(tag, "height")
    if width and height:
        if max(width, height) < 50 or width > 3.5 * height or height > 4 * width:
            return True
    elif (width and width < 50) or (height and height < 50):
        return True
    return False


def _int_attr(tag: Tag, name: str) -> int:
    match = re.match(r"\s*(\d+)", str(tag.get(name) or ""))
    return int(match.group(1)) if match else 0


def chrome_container_ids(soup: BeautifulSoup) -> set[int]:
    """ids of navigation/footer/site-header containers. Elements holding a large share of
    the page text are never treated as chrome (protects page-wide wrapper classes)."""
    body = soup.body or soup
    total = len(body.get_text(" ", strip=True)) or 1
    found: set[int] = set()
    for el in body.find_all(True):
        if el.name in ("nav", "footer"):
            found.add(id(el))
            continue
        chrome = bool(attr_tokens(el) & _CHROME_TOKENS)
        if not chrome and el.name == "header" and not el.find_parent(["main", "article", "section"]):
            chrome = el.find("nav") is not None or len(el.find_all("a", href=True)) >= 4
        if chrome and len(el.get_text(" ", strip=True)) <= 0.4 * total:
            found.add(id(el))
    return found


def in_containers(tag: Tag, container_ids: set[int]) -> bool:
    return any(id(ancestor) in container_ids for ancestor in tag.parents)


def collect_image_nodes(soup: BeautifulSoup, base_url: str, skip_chrome: bool = True) -> list[tuple[Tag, str]]:
    """(element, best_url) for every picture-like element that is not decoration."""
    found: list[tuple[Tag, str]] = []
    chrome = chrome_container_ids(soup) if skip_chrome else set()
    elements: Iterable[Tag] = soup.find_all(["img", "amp-img"])
    extra = soup.find_all(lambda t: t.name not in ("img", "amp-img", "source", "picture") and (
        any(t.has_attr(a) for a in _BG_ATTRS) or "url(" in (t.get("style") or "").lower()))
    for tag in list(elements) + list(extra):
        urls = image_urls(tag, base_url)
        if not urls:
            continue
        url = urls[0]
        if is_junk_image(tag, url) or (chrome and in_containers(tag, chrome)):
            continue
        found.append((tag, url))
    return found


# ---------------------------------------------------------------------------------------
# Links, pagination and page type
# ---------------------------------------------------------------------------------------


def is_social_or_external_profile(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return any(s in host for s in _SOCIAL_HOSTS)


def page_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """(absolute_url, anchor_text) for every link, including <select> navigation options."""
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        url = absolute_url(a["href"], base_url)
        if not url or url in seen:
            continue
        seen.add(url)
        text = a.get_text(" ", strip=True) or a.get("title") or ""
        if not text:
            img = a.find("img")
            text = (img.get("alt") or "") if img else ""
        links.append((url, re.sub(r"\s+", " ", text).strip()))
    for option in soup.find_all("option", value=True):
        value = option["value"].strip()
        if "/" in value or value.startswith("http"):
            url = absolute_url(value, base_url)
            if url and url not in seen:
                seen.add(url)
                links.append((url, option.get_text(" ", strip=True)))
    return links


def _listing_key(url: str) -> tuple[str, str, tuple]:
    parts = urlsplit(url)
    path = re.sub(r"/page/\d+/?$", "", parts.path).rstrip("/")
    query = tuple(sorted((k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _PAGE_PARAMS))
    host = parts.netloc.lower()
    return (host[4:] if host.startswith("www.") else host, path, query)


def pagination_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    """Links to further pages of the same listing (?page=2, /page/2/, rel=next, ...)."""
    current_key = _listing_key(page_url)
    candidates: list[str] = []
    for link in soup.select("a[rel~=next], link[rel~=next]"):
        candidates.append(link.get("href") or "")
    for container in soup.find_all(class_=re.compile(r"pagination|pager|page-numbers|nav-links|paging", re.I)):
        candidates.extend(a.get("href") or "" for a in container.find_all("a", href=True))
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True).lower()
        if text in _NEXT_TEXTS or (text.isdigit() and len(text) <= 3):
            candidates.append(a["href"])
    result: list[str] = []
    for href in candidates:
        url = absolute_url(href, page_url)
        if not url or canonical_url(url) == canonical_url(page_url) or url in result:
            continue
        if _listing_key(url) == current_key:
            result.append(url)
    return result


def looks_js_rendered(soup: BeautifulSoup) -> bool:
    """True if the HTML is an empty shell that needs JavaScript to show its content."""
    body = soup.body
    text = body.get_text(" ", strip=True) if body else ""
    scripts = len(soup.find_all("script"))
    if len(text) < 250 and scripts >= 2:
        return True
    shell = soup.find(id=re.compile(r"^(root|app|__next|__nuxt|q-app)$"))
    if shell is not None and len(shell.get_text(" ", strip=True)) < 200 and len(text) < 1500:
        return True
    if len(text) < 1500 and re.search(r"enable javascript|requires javascript|javascript is (?:disabled|required)", text, re.I):
        return True
    return False


def page_title(soup: BeautifulSoup) -> str:
    title = soup.find("title")
    return re.sub(r"\s+", " ", title.get_text(" ", strip=True)).strip() if title else ""


def meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""
