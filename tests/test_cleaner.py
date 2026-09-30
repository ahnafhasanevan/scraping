import pytest

from utils.cleaner import (
    clean_name,
    extract_emails,
    is_non_academic,
    looks_like_name,
    name_key,
    normalize_designation,
    safe_filename,
)


@pytest.mark.parametrize("value", [
    "Dr. Taskeed Jabid", "Prof. Dr. Md. Mozammel Huq Azad Khan", "Umana Anjalin, PhD", "KHADIZA BEGUM",
    "Md. Al-Imran", "A.K.M. Fazlul Hoque", "Professor Shams Rahman", "M. M. Fazle Rabbi", "Dr. Engr. Md. Sohag Miah",
])
def test_real_names_are_accepted(value):
    assert looks_like_name(value)


@pytest.mark.parametrize("value", [
    "Assistant Professor", "Asst. Prof.", "Faculty Members", "Read More", "Department of CSE", "View Profile",
    "Welcome to East West University", "Email: abc@ewubd.edu", "Our Faculty", "Chairperson", "Lab Assistant",
    "Dr. Abdul Karim Assistant Professor",
])
def test_non_names_are_rejected(value):
    assert not looks_like_name(value)


def test_clean_name_and_key():
    assert clean_name("Sadia Rabby (On Leave)") == "Sadia Rabby"
    assert clean_name("Dr. Nazia Hoque, Associate Professor") == "Dr. Nazia Hoque"
    assert name_key("Prof. Dr. Md. Rahman, PhD") == name_key("Md. Rahman")


def test_designations():
    assert normalize_designation("Asst. Prof. & Head") == "Assistant Professor & Head"
    assert normalize_designation("ASSOC. PROF.") == "Associate Professor"
    assert normalize_designation("Sr. Lecturer") == "Senior Lecturer"
    assert is_non_academic("Assistant Registrar")
    assert is_non_academic("Lab Assistant")
    assert not is_non_academic("Lecturer & Lab Coordinator")


def test_emails_and_filenames():
    assert extract_emails("rahman[at]ewubd[dot]edu, x.y@seu.edu.bd") == ["rahman@ewubd.edu", "x.y@seu.edu.bd"]
    assert safe_filename('Dr. X: "Y"/Z?') == "Dr. X Y Z"
    assert safe_filename("CON") == "_CON"
    assert len(safe_filename("A" * 300)) == 80
