"""Polite HTTP client: retries, per-site rate limiting, robots.txt, TLS fallback and
optional JavaScript rendering through Selenium (Chrome, Edge or Firefox)."""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("scraper.http")

_TWO_LEVEL_SUFFIXES = (".edu.bd", ".ac.bd", ".com.bd", ".gov.bd", ".org.bd", ".net.bd", ".co.uk", ".ac.uk")
_ROBOTS_AGENT = "FacultyScraper"


def site_key(url_or_host: str) -> str:
    """Registered domain used for rate limiting: 'fse.ewubd.edu' -> 'ewubd.edu'."""
    host = urlsplit(url_or_host).hostname if "//" in url_or_host else url_or_host
    host = (host or "").lower().rstrip(".")
    labels = host.split(".")
    keep = 3 if host.endswith(_TWO_LEVEL_SUFFIXES) else 2
    return ".".join(labels[-keep:])


@dataclass
class Page:
    url: str            # final URL after redirects
    requested_url: str
    html: str
    status: int
    rendered: bool = False


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        timeout: float = 25,
        max_retries: int = 3,
        request_delay: float = 1.5,
        image_delay: float = 0.4,
        respect_robots: bool = True,
        allow_insecure_fallback: bool = True,
        use_selenium: object = "auto",
        selenium_wait: float = 4,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.request_delay = request_delay
        self.image_delay = image_delay
        self.respect_robots = respect_robots
        self.allow_insecure_fallback = allow_insecure_fallback
        self.use_selenium = use_selenium
        self.selenium_wait = selenium_wait

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            }
        )

        self._lock = threading.Lock()
        self._next_slot: dict[tuple[str, str], float] = {}
        self._crawl_delay: dict[str, float] = {}
        self._insecure_hosts: set[str] = set()
        self._robots: dict[str, Optional[RobotFileParser]] = {}
        self._robots_lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._dead_hosts: set[str] = set()
        self._renderer: Optional[BrowserRenderer] = None
        self._renderer_failed = False
        self._render_lock = threading.Lock()

    # ------------------------------------------------------------------ rate limiting
    def _wait_turn(self, url: str, kind: str) -> None:
        key = site_key(url)
        delay = self.request_delay if kind == "page" else self.image_delay
        delay = max(delay, self._crawl_delay.get(key, 0.0) if kind == "page" else 0.0)
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get((key, kind), 0.0))
            self._next_slot[(key, kind)] = slot + delay
        if slot > now:
            time.sleep(slot - now)

    # ------------------------------------------------------------------ robots.txt
    def allowed_by_robots(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            if origin not in self._robots:
                self._robots[origin] = self._load_robots(origin)
            parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(_ROBOTS_AGENT, url)

    def _load_robots(self, origin: str) -> Optional[RobotFileParser]:
        try:
            resp = self._raw_get(origin + "/robots.txt", timeout=min(self.timeout, 12))
        except requests.RequestException:
            return None
        if resp is None or resp.status_code != 200 or "html" in resp.headers.get("Content-Type", "").lower():
            return None  # RFC 9309: a missing robots.txt means everything is allowed
        parser = RobotFileParser()
        parser.parse(resp.text.splitlines())
        delay = parser.crawl_delay(_ROBOTS_AGENT)
        if delay:
            self._crawl_delay[site_key(origin)] = min(float(delay), 15.0)
        return parser

    # ------------------------------------------------------------------ low level GET
    def _raw_get(self, url: str, timeout: Optional[float] = None, **kwargs) -> Optional[requests.Response]:
        host = urlsplit(url).hostname or ""
        verify = host not in self._insecure_hosts
        try:
            return self.session.get(url, timeout=timeout or self.timeout, verify=verify, **kwargs)
        except requests.exceptions.SSLError:
            if not self.allow_insecure_fallback or not verify:
                raise
            log.warning("TLS certificate problem on %s - retrying without certificate verification", host)
            self._insecure_hosts.add(host)
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            return self.session.get(url, timeout=timeout or self.timeout, verify=False, **kwargs)

    def _get(self, url: str, kind: str, referer: Optional[str] = None) -> Optional[requests.Response]:
        """GET with rate limiting, dead-host detection and an http<->https fallback."""
        host = urlsplit(url).hostname or ""
        if host in self._dead_hosts:
            return None
        if not self.allowed_by_robots(url):
            log.info("robots.txt disallows %s - skipped", url)
            return None
        headers = {"Referer": referer} if referer else {}
        if kind == "image":
            headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        candidates = [url]
        parts = urlsplit(url)
        if parts.scheme in ("http", "https"):
            other = "http" if parts.scheme == "https" else "https"
            candidates.append(urlunsplit((other,) + tuple(parts[1:])))
        last_error: Optional[Exception] = None
        for candidate in candidates:
            self._wait_turn(candidate, kind)
            try:
                resp = self._raw_get(candidate, headers=headers)
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError) as exc:
                last_error = exc
                continue
            except requests.RequestException as exc:
                log.debug("Request failed for %s: %s", candidate, exc)
                return None
            self._failures[host] = 0
            return resp
        failures = self._failures.get(host, 0) + 1
        self._failures[host] = failures
        log.debug("Could not connect to %s: %s", url, last_error)
        if failures >= 6 and host not in self._dead_hosts:
            self._dead_hosts.add(host)
            log.warning("Giving up on %s after %d connection failures", host, failures)
        return None

    # ------------------------------------------------------------------ public API
    def get_page(self, url: str, render: bool = False) -> Optional[Page]:
        """Fetch an HTML page. With render=True the page is loaded in a headless browser."""
        if render:
            return self.render(url)
        resp = self._get(url, "page")
        if resp is None:
            return None
        if resp.status_code >= 400:
            log.debug("HTTP %s for %s", resp.status_code, url)
            if resp.status_code in (403, 503) and self.can_render:
                return self.render(url)  # bot protection: a real browser often gets through
            return None
        content_type = resp.headers.get("Content-Type", "").lower()
        if content_type and not any(t in content_type for t in ("html", "xml", "text/plain")):
            log.debug("Skipping non-HTML content (%s) at %s", content_type, url)
            return None
        return Page(url=resp.url, requested_url=url, html=_decode_html(resp), status=resp.status_code)

    def get_binary(self, url: str, referer: Optional[str] = None) -> Optional[requests.Response]:
        resp = self._get(url, "image", referer=referer)
        if resp is None or resp.status_code >= 400:
            return None
        return resp

    @property
    def can_render(self) -> bool:
        return self.use_selenium not in (False, "never", "false", "no") and not self._renderer_failed

    def render(self, url: str) -> Optional[Page]:
        if not self.can_render or not self.allowed_by_robots(url):
            return None
        with self._render_lock:
            if self._renderer is None:
                try:
                    self._renderer = BrowserRenderer(self.user_agent, self.selenium_wait)
                except Exception as exc:  # selenium missing, no browser installed, ...
                    self._renderer_failed = True
                    log.warning(
                        "JavaScript rendering is unavailable (%s). Install Google Chrome or Microsoft Edge "
                        "and 'pip install selenium' to scrape JavaScript-only pages.", exc,
                    )
                    return None
            self._wait_turn(url, "page")
            try:
                final_url, html = self._renderer.render(url)
            except Exception as exc:
                log.debug("Rendering failed for %s: %s", url, exc)
                return None
        return Page(url=final_url, requested_url=url, html=html, status=200, rendered=True)

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        self.session.close()


def _decode_html(resp: requests.Response) -> str:
    content_type = resp.headers.get("Content-Type", "")
    if "charset=" in content_type.lower():
        return resp.text
    match = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", resp.content[:4096], re.I)
    encoding = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    try:
        return resp.content.decode(encoding, errors="replace")
    except LookupError:
        return resp.content.decode("utf-8", errors="replace")


class BrowserRenderer:
    """Headless browser used only for pages that need JavaScript."""

    LOAD_MORE_XPATH = (
        "//*[self::button or self::a][contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more') or "
        "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more') or "
        "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more') or "
        "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view more')]"
    )

    def __init__(self, user_agent: str, page_wait: float = 4):
        from selenium import webdriver  # imported lazily: selenium is optional

        self.page_wait = page_wait
        errors = []
        self.driver = None
        for name in ("chrome", "edge", "firefox"):
            try:
                if name == "chrome":
                    opts = webdriver.ChromeOptions()
                elif name == "edge":
                    opts = webdriver.EdgeOptions()
                else:
                    opts = webdriver.FirefoxOptions()
                if name == "firefox":
                    opts.add_argument("-headless")
                    opts.set_preference("general.useragent.override", user_agent)
                else:
                    for arg in ("--headless=new", "--disable-gpu", "--no-sandbox", "--window-size=1366,2400",
                                "--ignore-certificate-errors", f"--user-agent={user_agent}", "--log-level=3"):
                        opts.add_argument(arg)
                opts.accept_insecure_certs = True
                driver_cls = {"chrome": webdriver.Chrome, "edge": webdriver.Edge, "firefox": webdriver.Firefox}[name]
                self.driver = driver_cls(options=opts)
                self.driver.set_page_load_timeout(60)
                log.info("JavaScript rendering enabled with headless %s", name.capitalize())
                break
            except Exception as exc:  # try the next browser
                errors.append(f"{name}: {str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__}")
        if self.driver is None:
            raise RuntimeError("; ".join(errors))

    def render(self, url: str) -> tuple[str, str]:
        from selenium.common.exceptions import WebDriverException

        driver = self.driver
        driver.get(url)
        time.sleep(self.page_wait)
        last_height = 0
        for _ in range(12):  # scroll to trigger lazy-loaded images / infinite lists
            height = driver.execute_script("return document.body ? document.body.scrollHeight : 0") or 0
            driver.execute_script("window.scrollTo(0, arguments[0]);", height)
            time.sleep(0.8)
            if height == last_height:
                break
            last_height = height
        for _ in range(10):  # press "load more" buttons
            buttons = [b for b in driver.find_elements("xpath", self.LOAD_MORE_XPATH) if b.is_displayed()]
            if not buttons:
                break
            try:
                driver.execute_script("arguments[0].click();", buttons[0])
            except WebDriverException:
                break
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        return driver.current_url, driver.page_source

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass
