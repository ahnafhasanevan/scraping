"""A fake university website served on localhost, used by the end-to-end test.

It mixes the layouts found on the real sites: a card grid with pagination, a table with a
lab-staff row, a flat layout, names-only links to profile pages, a JavaScript (Next.js)
page, WordPress-style thumbnails, placeholder avatars and a robots.txt rule.
"""
from __future__ import annotations

import io
import json
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image


def make_jpeg(color: tuple, size=(200, 240)) -> bytes:
    """A photo-like JPEG: solid colour plus deterministic noise (realistic file size)."""
    rng = random.Random(hash(color) ^ size[0])
    noise = Image.frombytes("RGB", size, rng.randbytes(size[0] * size[1] * 3))
    image = Image.blend(Image.new("RGB", size, color), noise, 0.35)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def make_png(color: tuple, size=(300, 80)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


CHROME = """
<header class="site-header"><a href="/"><img src="/assets/img/logo.png" alt="Mock University logo"></a>
<nav class="navbar"><ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li>
<li><a href="/academics/">Academics</a></li><li><a href="/news/">News</a></li><li><a href="/contact">Contact</a></li></ul></nav>
</header>"""
FOOTER = """<footer><img src="/assets/img/footer-logo.png"><a href="https://facebook.com/mock"><img src="/assets/img/facebook.png"></a>
<p>Copyright Mock University</p></footer>"""


def page(title: str, body: str, head: str = "") -> str:
    return (f"<!doctype html><html><head><title>{title}</title>"
            f"<meta property='og:image' content='/assets/img/share.jpg'>{head}</head>"
            f"<body>{CHROME}<main>{body}</main>{FOOTER}</body></html>")


def card(slug: str, name: str, designation: str, img: str) -> str:
    return f"""<div class="col-md-3"><div class="card faculty-card">
<a href="/faculty-view/{slug}"><img class="card-img-top" src="{img}" alt="{name}"></a>
<div class="card-body"><h5 class="card-title">{name}</h5><p class="designation">{designation}</p>
<p>Email: {slug}[at]mock[dot]edu</p></div></div></div>"""


def build_site() -> tuple[dict, dict]:
    pages: dict[str, str] = {}
    files: dict[str, tuple[bytes, str]] = {}

    pages["/"] = page("Mock University", """<h1>Welcome to Mock University</h1>
<div class="hero-slider"><img src="/assets/img/slider-1.jpg" alt="Campus"></div>
<div class="leaders">""" + card("vc", "Prof. Dr. Vice Person", "Vice Chancellor", "/storage/leaders/vc.jpg")
        + card("pvc", "Prof. Dr. Pro Person", "Pro Vice Chancellor", "/storage/leaders/pvc.jpg") + """</div>
<p><a href="/academics/">Our Departments</a></p>""")
    # A "soft 404": status 200, but an error page (with people cards that must be ignored).
    pages["/department-of-math/faculty-members"] = page(
        "Page Not Found", "<h1>404 - Page Not Found</h1><div class='row'>"
        + "".join(card(f"x{i}", f"Dr. Wrong Person{c}", "Professor", f"/storage/wrong/{i}.jpg") for i, c in enumerate("ABC"))
        + "</div>")
    pages["/academics/"] = page("Academics", """<h2>Departments</h2><ul>
<li><a href="/department-of-cse/">Department of CSE</a></li>
<li><a href="/department-of-eee/">Department of EEE</a></li>
<li><a href="/department-of-law/">Department of Law</a></li>
<li><a href="/department-of-english/">Department of English</a></li>
<li><a href="/department-of-bba/">Department of Business Administration</a></li>
<li><a href="/private/faculty-members">Secret faculty</a></li></ul>""")
    pages["/department-of-cse/"] = page("Department of CSE", """<h1>Department of Computer Science and Engineering</h1>
<p>Message from the chairperson ...</p><a href="/department-of-cse/faculty-members">Faculty Members</a>""")
    cse1 = [
        ("rahman", "Dr. Abdur Rahman", "Professor & Chairperson", "/wp-content/uploads/2024/01/rahman-150x150.jpg"),
        ("karim", "Dr. Fazlul Karim", "Associate Professor", "/storage/faculty/karim.jpg"),
        ("akter", "Ms. Nasrin Akter", "Asst. Prof.", "/storage/faculty/akter.jpg"),
        ("hasan", "Md. Mahmudul Hasan", "Lecturer", "/storage/faculty/hasan.jpg"),
    ]
    cse2 = [
        ("islam", "Tahmina Islam", "Senior Lecturer", "/storage/faculty/islam.jpg"),
        ("chowdhury", "Sadia Chowdhury", "Lecturer", "/assets/img/default-avatar.png"),
    ]
    pager = """<ul class="pagination"><li class="active"><span>1</span></li><li><a href="/department-of-cse/faculty-members?page=2">2</a></li>
<li><a rel="next" href="/department-of-cse/faculty-members?page=2">Next</a></li></ul>"""
    pages["/department-of-cse/faculty-members"] = page(
        "Faculty Members - Department of CSE",
        "<h2>Faculty Members</h2><div class='row'>" + "".join(card(*c) for c in cse1) + "</div>" + pager)
    pages["/department-of-cse/faculty-members?page=2"] = page(
        "Faculty Members - Department of CSE",
        "<h2>Faculty Members</h2><div class='row'>" + "".join(card(*c) for c in cse2) + "</div>")

    pages["/department-of-eee/"] = page("Department of EEE", "<a href='/department-of-eee/faculty.html'>Our Faculty</a>")
    pages["/department-of-eee/faculty.html"] = page("Full Time Faculty - EEE", """<table>
<tr><td><img src="images/iftekhar.jpg" width="120" height="150"></td><td><b>Dr. Iftekhar Anam</b><br>Professor<br>Ph.D., Texas A&amp;M University</td></tr>
<tr><td><img src="images/tamanna.jpg" width="120" height="150"></td><td><b>Dr. Afifa Tamanna</b><br>Assistant Professor</td></tr>
<tr><td><img src="images/kamal.jpg" width="120" height="150"></td><td><b>Md. Kamal Hossain</b><br>Lab Assistant</td></tr>
</table>""")

    pages["/department-of-law/"] = page("Department of Law", "<a href='/department-of-law/teaching-staff'>Teaching Staff</a>")
    pages["/department-of-law/teaching-staff"] = page("Teaching Staff | Department of Law", """
<div class="content"><img src="/uploads/law/parvez.jpg"><h4>Professor Dr. Parvez Ahmed</h4><p>Professor and Head</p>
<img src="/uploads/law/jahid.jpg"><h4>Abdullah Al Jahid</h4><p>Senior Lecturer</p></div>
<h3>Adjunct faculty</h3><ul><li><a href="/faculty-view/quader">Nazifa Muniyat Quader</a></li>
<li><a href="/faculty-view/sultana">View Profile</a></li></ul>""")

    pages["/department-of-english/"] = page("Department of English", "<a href='/department-of-english/faculty-members'>Faculty Members</a>")
    english = [("e1", "Rezina Sultana", "Associate Professor", "/uploads/en/1/pic.jpg"),
               ("e2", "Shahbaz Khan", "Lecturer", "/uploads/en/2/pic.jpg"),
               ("e3", "Arifa Rahman", "Lecturer", "/uploads/en/3/pic.jpg"),
               ("e4", "Moriam Quadir", "Professor", "/uploads/en/4/pic.jpg")]
    pages["/department-of-english/faculty-members"] = page(
        "Faculty Members - Department of English",
        "<div class='row'>" + "".join(card(*c) for c in english) + "</div>")

    next_data = {"props": {"pageProps": {"faculty": [
        {"name": "Benazir Rahman", "designation": "Assistant Professor", "image": {"url": "/uploads/bba/benazir.jpg"}},
        {"name": "Zahurul Alam", "designation": "Professor", "photo": "/_next/image?url=%2Fuploads%2Fbba%2Fzahurul.jpg&w=640&q=75"},
    ]}}}
    pages["/department-of-bba/"] = page("Department of Business Administration", "<a href='/department-of-bba/faculty'>Faculty</a>")
    pages["/department-of-bba/faculty"] = (
        "<html><head><title>Faculty</title></head><body><div id='__next'></div>"
        f"<script id='__NEXT_DATA__' type='application/json'>{json.dumps(next_data)}</script>"
        "<script src='/_next/a.js'></script><script src='/_next/b.js'></script></body></html>")

    for slug, name, designation, photo in [
        ("chowdhury", "Sadia Chowdhury", "Lecturer", "/storage/faculty/chowdhury-real.jpg"),
        ("quader", "Nazifa Muniyat Quader", "Adjunct Faculty", "/storage/faculty/quader.jpg"),
        ("sultana", "Dr. Kohinoor Sultana", "Adjunct Professor", "/storage/faculty/sultana.jpg"),
    ]:
        pages[f"/faculty-view/{slug}"] = page(f"{name} - Faculty view", f"""<div class="breadcrumb"><a href="/">Home</a> / Faculty</div>
<div class="row"><div class="col-md-4 profile-photo"><img src="{photo}" alt="{name}"></div>
<div class="col-md-8"><h1>{name}</h1><p>{designation}</p><p>Email: {slug}@mock.edu</p></div></div>""")
    for slug, *_ in cse1 + cse2 + english:
        pages.setdefault(f"/faculty-view/{slug}", page("Faculty view", f"<h1>{slug}</h1>"))

    pages["/private/faculty-members"] = page("Private", "<div class='row'>" + card("secret", "Dr. Secret Person", "Professor", "/storage/faculty/secret.jpg") + "</div>")
    files["/robots.txt"] = (b"User-agent: *\nDisallow: /private/\n", "text/plain")

    colours = iter([(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (30, 200, 200), (200, 30, 200),
                    (120, 60, 30), (60, 120, 30), (30, 60, 120), (90, 90, 90), (150, 20, 90), (20, 150, 90),
                    (90, 20, 150), (160, 160, 60), (60, 160, 160), (160, 60, 160), (10, 10, 10), (240, 240, 240)])
    for path in ["/wp-content/uploads/2024/01/rahman.jpg", "/storage/faculty/karim.jpg", "/storage/faculty/akter.jpg",
                 "/storage/faculty/hasan.jpg", "/storage/faculty/islam.jpg", "/storage/faculty/chowdhury-real.jpg",
                 "/department-of-eee/images/iftekhar.jpg", "/department-of-eee/images/tamanna.jpg",
                 "/department-of-eee/images/kamal.jpg", "/uploads/law/parvez.jpg", "/uploads/law/jahid.jpg",
                 "/storage/faculty/quader.jpg", "/storage/faculty/sultana.jpg", "/uploads/bba/benazir.jpg",
                 "/uploads/bba/zahurul.jpg", "/storage/faculty/secret.jpg"]:
        files[path] = (make_jpeg(next(colours), (400, 480)), "image/jpeg")
    files["/wp-content/uploads/2024/01/rahman-150x150.jpg"] = (make_jpeg((200, 30, 30), (150, 150)), "image/jpeg")
    same_placeholder = make_jpeg((128, 128, 128))
    for i in (1, 2, 3):
        files[f"/uploads/en/{i}/pic.jpg"] = (same_placeholder, "image/jpeg")
    files["/uploads/en/4/pic.jpg"] = (make_jpeg((5, 100, 5)), "image/jpeg")
    files["/assets/img/logo.png"] = (make_png((0, 0, 0)), "image/png")
    files["/assets/img/share.jpg"] = (make_jpeg((1, 1, 1)), "image/jpeg")
    return pages, files


REDIRECTS = {"/department-of-chemistry/faculty-members": "/"}  # guessed URL -> home page


class MockSite:
    def __init__(self):
        self.pages, self.files = build_site()
        self.requests: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (http.server naming)
                site.requests.append(self.path)
                if self.path in REDIRECTS:
                    self.send_response(302)
                    self.send_header("Location", REDIRECTS[self.path])
                    self.end_headers()
                    return
                if self.path in site.pages:
                    body, ctype = site.pages[self.path].encode("utf-8"), "text/html; charset=utf-8"
                elif self.path.split("?")[0] in site.files:
                    body, ctype = site.files[self.path.split("?")[0]]
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body>Not found</body></html>")
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
