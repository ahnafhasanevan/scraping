import json
import re

from bs4 import BeautifulSoup

from utils.extractor import (
    candidate_profile_links,
    extract_cards,
    extract_json_records,
    extract_profile,
    extract_table_rows,
    unwrap_image_proxy,
)
from utils.html_tools import looks_js_rendered, pagination_links
from utils.image_downloader import full_size_variants

URL = "https://fse.ewubd.edu/computer-science-engineering/faculty-members"
CHROME = """<header class="site-header"><a href="/"><img src="/assets/img/logo.png" alt="logo"></a>
<nav class="navbar"><a href="/">Home</a><a href="/about">About</a><a href="/news">News</a><a href="/contact">Contact</a></nav></header>"""
FOOTER = "<footer><img src='/img/footer-logo.png'><a href='https://facebook.com/x'><img src='/img/fb.png'></a></footer>"


def soup_of(body: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><head><title>Faculty Members</title></head><body>{CHROME}<main>{body}</main>{FOOTER}</body></html>", "lxml")


def by_name(records):
    return {r["name"]: r for r in records}


def test_bootstrap_card_grid():
    cards = "".join(f"""<div class="col-md-3"><div class="card">
      <a href="/cse/faculty-view/p{i}"><img class="card-img-top" src="/storage/faculty/p{i}.jpg" alt="{n}"></a>
      <div class="card-body"><h5 class="card-title">{n}</h5><p class="designation">{d}</p>
      <p>Email: p{i}[at]ewubd[dot]edu</p></div></div></div>"""
                    for i, (n, d) in enumerate([("Dr. Taskeed Jabid", "Professor"),
                                                ("Dr. Maheen Islam", "Professor & Chairperson"),
                                                ("Amit Mandal", "Senior Lecturer")]))
    records = by_name(extract_cards(soup_of(f"<div class='row'>{cards}</div>"), URL))
    assert set(records) == {"Dr. Taskeed Jabid", "Dr. Maheen Islam", "Amit Mandal"}
    taskeed = records["Dr. Taskeed Jabid"]
    assert taskeed["designation"] == "Professor"
    assert taskeed["email"] == "p0@ewubd.edu"
    assert taskeed["profile_url"] == "https://fse.ewubd.edu/cse/faculty-view/p0"
    assert taskeed["photo_url"] == "https://fse.ewubd.edu/storage/faculty/p0.jpg"


def test_table_rows_with_photos():
    rows = "".join(f"<tr><td><img src='images/f{i}.jpg' width='120' height='150'></td><td><b>{n}</b><br>{d}</td></tr>"
                   for i, (n, d) in enumerate([("Dr. Iftekhar Anam", "Professor"), ("Dr. Afifa Tamanna", "Assistant Professor")]))
    records = by_name(extract_cards(soup_of(f"<table>{rows}</table>"), "https://ce.uap-bd.edu/faculty.html"))
    assert records["Dr. Afifa Tamanna"]["designation"] == "Assistant Professor"
    assert records["Dr. Iftekhar Anam"]["photo_url"] == "https://ce.uap-bd.edu/images/f0.jpg"


def test_flat_layout_uses_sibling_text():
    body = ("<div class='content'><img src='/f/a.jpg'><h4>Dr. Abdur Rahman</h4><p>Lecturer</p>"
            "<img src='/f/b.jpg'><h4>Ms. Bilkis Akter</h4><p>Senior Lecturer</p></div>")
    records = by_name(extract_cards(soup_of(body), URL))
    assert records["Ms. Bilkis Akter"]["photo_url"].endswith("/f/b.jpg")
    assert records["Ms. Bilkis Akter"]["designation"] == "Senior Lecturer"


def test_lazy_loaded_srcset_and_abbreviated_designation():
    cards = "".join(f"""<div class="team-member"><img src="data:image/gif;base64,R0lGOD" class="lazyload"
      data-src="/wp-content/uploads/2023/05/m{i}-150x150.jpg"
      data-srcset="/wp-content/uploads/2023/05/m{i}-150x150.jpg 150w, /wp-content/uploads/2023/05/m{i}.jpg 600w">
      <h3 class="team-name"><a href="/faculty/m{i}/">Md. Rafiqul Islam{chr(65 + i)}</a></h3>
      <span class="team-position">Asst. Prof.</span></div>""" for i in range(3))
    records = extract_cards(soup_of(cards), URL)
    assert len(records) == 3
    assert records[0]["designation"] == "Assistant Professor"
    assert records[0]["photo_url"].endswith("/wp-content/uploads/2023/05/m0.jpg")


def test_css_background_photos():
    cards = "".join(f"""<div class="person"><div class="person-photo" style="background-image: url('/media/faculty/k{i}.jpg')"></div>
      <h3>Dr. Karim Uddin{chr(65 + i)}</h3><span>Associate Professor</span></div>""" for i in range(2))
    records = extract_cards(soup_of(cards), URL)
    assert [r["photo_url"].rsplit("/", 1)[-1] for r in records] == ["k0.jpg", "k1.jpg"]


def test_logos_banners_and_news_are_ignored():
    body = """<div class="hero-slider"><img src="/uploads/slider/campus.jpg" alt="Welcome to EWU"></div>
      <div class="news-item"><img src="/uploads/news/convocation.jpg"><h4>Convocation held</h4></div>"""
    assert extract_cards(soup_of(body), URL) == []


def test_placeholder_avatar_is_not_used_as_photo():
    body = """<div class="card"><img src="/assets/img/default-avatar.png"><h5>Sadia Chowdhury</h5><p>Lecturer</p>
      <a href="/faculty-view/sadia">View Profile</a></div>"""
    [record] = extract_cards(soup_of(body), URL)
    assert record["photo_url"] == ""
    assert record["profile_url"].endswith("/faculty-view/sadia")


def test_plain_table_without_photos():
    table = """<table><tr><th>Name</th><th>Designation</th></tr>
      <tr><td><a href="/faculty/profile/1">Dr. Nazia Hoque</a></td><td>Associate Professor</td><td>nazia@ewubd.edu</td></tr></table>"""
    [record] = extract_table_rows(soup_of(table), URL)
    assert record["name"] == "Dr. Nazia Hoque"
    assert record["email"] == "nazia@ewubd.edu"


def test_nextjs_and_inertia_json():
    next_data = {"props": {"pageProps": {"faculty": [
        {"name": "Abdul Awal", "designation": "Lecturer", "image": {"url": "/uploads/abdul.jpg"}},
        {"name": "Atia Akter", "designation": "Lecturer", "photo": "/_next/image?url=%2Fuploads%2Fatia.png&w=640&q=75"}]}}}
    html = (f"<html><body><div id='__next'></div><script id='__NEXT_DATA__' type='application/json'>{json.dumps(next_data)}</script>"
            "<script src='/a.js'></script><script src='/b.js'></script></body></html>")
    soup = BeautifulSoup(html, "lxml")
    assert looks_js_rendered(soup)
    records = by_name(extract_json_records(soup, "https://eub.edu.bd/department-of-ipe/1000/"))
    assert records["Atia Akter"]["photo_url"] == "https://eub.edu.bd/uploads/atia.png"
    assert records["Abdul Awal"]["photo_url"] == "https://eub.edu.bd/uploads/abdul.jpg"

    page = json.dumps({"props": {"members": [{"name": "Dr. Farhana Huq", "designation": "Assistant Professor",
                                               "photo": "/storage/faculty/farhana.jpg"}]}}).replace("'", "&#39;")
    soup = BeautifulSoup(f"<html><body><div id='app' data-page='{page}'></div></body></html>", "lxml")
    [record] = extract_json_records(soup, URL)
    assert record["name"] == "Dr. Farhana Huq"


def test_profile_page():
    body = """<div class="breadcrumb"><a href="/">Home</a> / Faculty</div>
      <div class="profile-img"><img src="/storage/faculty/taskeed_jabid.jpg" alt="Taskeed Jabid"></div>
      <h1>Dr. Taskeed Jabid</h1><p>Professor</p><p>Department of Computer Science and Engineering</p>
      <p>Email: taskeed@ewubd.edu</p><p>Ph.D. in Computer Engineering, Kyung Hee University</p>
      <p>Research Interests: Computer Vision, Machine Learning</p>
      <div class="sidebar-news"><img src="/storage/news/convocation.jpg" alt="Convocation"></div>"""
    record = extract_profile(soup_of(body), "https://fse.ewubd.edu/computer-science-engineering/faculty-view/taskeed")
    assert record["name"] == "Dr. Taskeed Jabid"
    assert record["designation"] == "Professor"
    assert record["photo_url"].endswith("/storage/faculty/taskeed_jabid.jpg")
    assert record["department_hint"] == "Computer Science and Engineering"
    assert record["research_interests"] == "Computer Vision, Machine Learning"


def test_pagination_and_profile_links():
    body = """<ul class="pager"><li><a href="/people/ba-faculty?page=1">2</a></li><li class="pager-next"><a href="/people/ba-faculty?page=1">next ›</a></li></ul>
      <a href="/news?page=2">2</a>"""
    assert pagination_links(soup_of(body), "https://ulab.edu.bd/people/ba-faculty") == ["https://ulab.edu.bd/people/ba-faculty?page=1"]

    body = """<ul><li><a href="/faculty-profile.php?id=96">Mohammad Jahidul Azad</a></li><li><a href="/about-us">About Us</a></li>
      <li><a href="/department/member_details/145">View Profile</a></li></ul>"""
    links = candidate_profile_links(soup_of(body), "https://bubt.edu.bd/x", [re.compile(r"member_details/\d+")])
    assert links == [("https://bubt.edu.bd/faculty-profile.php?id=96", "Mohammad Jahidul Azad"),
                     ("https://bubt.edu.bd/department/member_details/145", "")]


def test_full_size_url_variants():
    assert full_size_variants("https://x.bd/wp-content/uploads/2023/05/a-150x150.jpg")[0] == "https://x.bd/wp-content/uploads/2023/05/a.jpg"
    assert full_size_variants("https://ulab.edu.bd/sites/default/files/styles/thumb/public/faculty/a.jpg?itok=Ab1")[0] == \
        "https://ulab.edu.bd/sites/default/files/faculty/a.jpg"
    assert unwrap_image_proxy("https://eub.edu.bd/_next/image?url=%2Fimg%2Fa.jpg&w=64") == "https://eub.edu.bd/img/a.jpg"


def test_wordpress_author_json_ld_is_not_a_faculty_member():
    graph = {"@graph": [{"@type": "Person", "@id": "https://x.bd/#/schema/person/abc", "name": "Web Admin",
                         "image": {"@type": "ImageObject", "url": "https://secure.gravatar.com/avatar/1"}},
                        {"@type": "Person", "name": "Md Rahim Uddin", "image": "https://secure.gravatar.com/avatar/2",
                         "jobTitle": "Editor"}]}
    soup = BeautifulSoup(f"<html><body><script type='application/ld+json'>{json.dumps(graph)}</script></body></html>", "lxml")
    assert extract_json_records(soup, URL) == []


def test_profile_name_prefers_main_heading_over_sidebar():
    body = """<aside><h3>Dr. Sidebar Person</h3><p>Chairperson</p></aside>
      <h1>Dr. Main Person</h1><img src="/storage/faculty/main_person.jpg" alt="Main Person"><p>Lecturer</p>"""
    record = extract_profile(soup_of(body), "https://fse.ewubd.edu/cse/faculty-view/main")
    assert record["name"] == "Dr. Main Person"
    assert record["photo_url"].endswith("main_person.jpg")
