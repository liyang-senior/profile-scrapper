"""Tests for search URL parsing and profile row mapping."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extract.api_client import _profile_to_row, _search_body_from_url
from extract.profile_photo import (
    is_getprog_photo,
    progai_avatar_from_linkedin,
    resolve_profile_photo,
)

from extract.search_params import build_search_body, normalize_search, search_from_url


def test_search_body_from_url():
    url = (
        "https://app.getprog.ai/search/results?"
        "locations[]=California&page=0&seniority[]=Senior&size=100&"
        "text=Senior%20ML%20engineers"
    )
    body = _search_body_from_url(url, page=2, size=100)
    assert body["page"] == 2
    assert body["size"] == 100
    assert body["locations"] == ["California"]
    assert body["seniority"] == ["Senior"]
    assert "ML" in body["text"]


def test_build_search_body():
    search = search_from_url(
        "https://app.getprog.ai/search/results?"
        "countries[]=United%20States&locations[]=Texas&text=Senior%20ML%20Engineer"
    )
    body = build_search_body(search, page=0, size=100)
    assert body["countries"] == ["United States"]
    assert body["locations"] == ["Texas"]
    assert "ML" in body["text"]


def test_build_search_body_languages_as_list():
    search = normalize_search(
        {"text": "engineer", "languages": ["English", "Chinese"], "countries": ["United States"]}
    )
    body = build_search_body(search, page=0, size=100)
    assert body["languages"] == ["English", "Chinese"]
    assert isinstance(body["languages"], list)


def test_build_search_body_female_first_name():
    search = normalize_search(
        {"text": "engineer", "is_first_name_female": True, "locations": ["New York, New York"]}
    )
    body = build_search_body(search, page=0, size=100)
    assert body["is_first_name_female"] == "true"


def test_validate_search_requires_geo():
    from extract.search_params import validate_search

    try:
        validate_search({"text": "engineer"})
        assert False, "expected geo validation error"
    except RuntimeError as exc:
        assert "Country" in str(exc) or "Location" in str(exc)


def test_build_search_body_yo_as_list():
    search = normalize_search(
        {"text": "engineer", "yo_employement": ["5-10"], "countries": ["United States"]}
    )
    body = build_search_body(search, page=0, size=100)
    assert "yo_employment" in body
    assert body["yo_employment"] == ["5-10"]
    assert isinstance(body["yo_employment"], list)
    assert "yo_employement" not in body


def test_format_api_error_validation():
    import httpx
    from extract.search_params import format_api_error

    resp = httpx.Response(400, json={"seniority": [["\"Invalid\" is not a valid choice."]]})
    msg = format_api_error(resp)
    assert "seniority" in msg
    assert "Invalid" in msg

    empty_geo = httpx.Response(400, content=b"")
    msg = format_api_error(empty_geo)
    assert "Country" in msg or "Location" in msg

    empty_with_geo = httpx.Response(400, content=b"")
    msg = format_api_error(empty_with_geo, {"countries": ["United States"], "text": "engineer"})
    assert "Country/location is set" in msg or "already set" in msg.lower()


def test_profile_has_emails_empty_list_string():
    from extract.api_client import _profile_has_emails, _profile_needs_email_enrichment

    profile = {
        "full_name": "Grace Nneji",
        "emails": "[]",
        "primary_email": None,
        "profile_pic_url": "https://s3.us-west-1.amazonaws.com/progai-linkedin-avatars/x.png",
    }
    assert not _profile_has_emails(profile)
    assert _profile_needs_email_enrichment(profile)

    with_email = {
        "emails": "['test@example.com']",
        "primary_email": None,
    }
    assert _profile_has_emails(with_email)
    assert not _profile_needs_email_enrichment(with_email)


def test_profile_has_emails_primary():
    from extract.api_client import _profile_has_emails

    assert _profile_has_emails({"primary_email": "a@b.com", "emails": "[]"})


def test_search_fallback_bodies():
    from extract.search_params import search_fallback_bodies

    body = {
        "text": "engineer",
        "page": 0,
        "size": 100,
        "countries": ["United States"],
        "yo_experience": ["5-10"],
        "yo_employment": ["5-10"],
        "is_first_name_female": True,
        "with_emails": True,
    }
    labels = [label for label, _ in search_fallback_bodies(body)]
    assert len(labels) >= 1
    assert "omit with_emails" in labels[0]


def test_infer_seniority_from_text():
    search = normalize_search({"text": "Senior ML Engineer", "countries": ["United States"]})
    assert search["seniority"] == ["Senior"]


def test_job_queries_from_search():
    from extract.search_params import job_queries_from_search

    assert job_queries_from_search({"text": "Senior ML Engineer"}) == ["Senior ML Engineer"]
    assert job_queries_from_search(
        {
            "text": "AI Engineer\nML Engineer\nData Engineer\nProduct Manager\nDevOps Engineer"
        }
    ) == [
        "AI Engineer",
        "ML Engineer",
        "Data Engineer",
        "Product Manager",
        "DevOps Engineer",
    ]
    assert job_queries_from_search({"text": "Product Manager\nproduct manager\n"}) == [
        "Product Manager"
    ]


def test_role_to_tab_product_and_devops():
    from parse.role_groups import role_to_tab

    assert role_to_tab("Product Manager") == "Product Manager"
    assert role_to_tab("senior product manager") == "Product Manager"
    assert role_to_tab("PRODUCT MANAGER, Growth") == "Product Manager"
    assert role_to_tab("DevOps Engineer") == "DevOps Engineer"
    assert role_to_tab("senior devops engineer") == "DevOps Engineer"
    assert role_to_tab("DEVOPS ENGINEER") == "DevOps Engineer"
    assert role_to_tab("Dev-Ops Engineer") == "DevOps Engineer"
    assert role_to_tab("Data Engineer") == "Data Engineer"
    assert role_to_tab("senior data engineer") == "Data Engineer"
    assert role_to_tab("DATA ENGINEER") == "Data Engineer"
    assert role_to_tab("AI Engineer") == "AI Engineer"
    assert role_to_tab("ml engineer") == "ML Engineer"
    assert role_to_tab("Machine Learning Engineer") == "ML Engineer"
    assert role_to_tab("Full Stack Engineer") == "Full Stack Engineer"
    assert role_to_tab("senior fullstack engineer") == "Full Stack Engineer"
    assert role_to_tab("Full-Stack Developer") == "Full Stack Engineer"
    assert role_to_tab("BI Engineer") == "BI Engineer"
    assert role_to_tab("Business Intelligence Engineer") == "BI Engineer"
    assert role_to_tab("bi analyst") == "BI Engineer"
    assert role_to_tab("Software Engineer") == "Software Engineer"
    assert role_to_tab("backend engineer") == "Software Engineer"


def test_row_has_email():
    from extract.api_client import row_has_email

    assert row_has_email({"email": "a@gmail.com"})
    assert row_has_email({"email": "a@gmail.com\nb@company.com"})
    assert not row_has_email({"email": "a@company.com"})
    assert not row_has_email({"email": ""})
    assert not row_has_email({"email": "[]"})
    assert not row_has_email({})


def test_gmail_only_emails():
    from extract.api_client import gmail_only_emails, is_gmail_address

    assert is_gmail_address("x@gmail.com")
    assert is_gmail_address("x@googlemail.com")
    assert not is_gmail_address("x@acme.com")
    assert gmail_only_emails(["a@acme.com", "b@gmail.com", "c@corp.io"]) == ["b@gmail.com"]


def test_profile_to_row():
    profile = {
        "id": 1,
        "full_name": "Jane Doe",
        "title": "Senior Engineer at Acme 5 y experience",
        "company": "Acme",
        "profile_pic_url": "https://example.com/p.jpg",
        "primary_email": "jane@acme.com",
        "emails": ["jane@acme.com", "jane.doe@gmail.com"],
        "linkedin_url": "https://linkedin.com/in/jane",
        "years_of_experience": 5,
        "skills": ["python", "ml"],
    }
    row = _profile_to_row(profile, {"score": 0.9, "reasons": ["skill match"]})
    assert row["name"] == "Jane Doe"
    assert row["email"] == "jane.doe@gmail.com"
    assert row["sender"] == ""
    assert row["sent"] == ""
    assert row["photo"] == "https://example.com/p.jpg"
    assert "profile_id" not in row


def test_profile_to_row_drops_company_only():
    profile = {
        "id": 2,
        "full_name": "Bob Corp",
        "title": "Engineer",
        "company": "Acme",
        "primary_email": "bob@acme.com",
        "emails": ["bob@acme.com"],
        "linkedin_url": "https://linkedin.com/in/bob",
    }
    row = _profile_to_row(profile)
    assert row["email"] == ""
    assert not __import__("extract.api_client", fromlist=["row_has_email"]).row_has_email(row)


def test_photo_initials_fallback():
    profile = {
        "first_name": "Analysa",
        "last_name": "Gonzales",
        "full_name": "Analysa Gonzales",
        "profile_pic_url": "",
    }
    photo = resolve_profile_photo(profile)
    assert photo.startswith("https://ui-avatars.com/api/")
    assert "Analysa" in photo


def test_photo_github_fallback():
    profile = {
        "full_name": "Dev User",
        "github_handle": "octocat",
        "profile_pic_url": "",
    }
    photo = resolve_profile_photo(profile)
    assert photo == "https://avatars.githubusercontent.com/octocat?v=4"


def test_progai_avatar_from_linkedin():
    url = progai_avatar_from_linkedin("https://linkedin.com/in/mirayyuce")
    assert "progai-linkedin-avatars/mirayyuce.png" in url


def test_photo_linkedin_guess_when_api_omits_pic():
    profile = {
        "full_name": "Miray Yuce",
        "linkedin_url": "https://linkedin.com/in/mirayyuce",
        "profile_pic_url": "",
    }
    photo = resolve_profile_photo(profile)
    assert is_getprog_photo(photo)


def test_photo_trusts_api_url_like_getprog():
    s3 = "https://s3.us-west-1.amazonaws.com/progai-linkedin-avatars/ecdedios.png"
    profile = {
        "full_name": "Ednalyn De Dios",
        "github_handle": "ecdedios",
        "profile_pic_url": s3,
    }
    assert resolve_profile_photo(profile) == s3


def test_photo_validate_urls_can_replace_broken_s3():
    profile = {
        "full_name": "Ednalyn De Dios",
        "github_handle": "ecdedios",
        "profile_pic_url": "https://s3.us-west-1.amazonaws.com/progai-linkedin-avatars/ecdedios.png",
    }
    photo = resolve_profile_photo(profile, validate_urls=True)
    assert "progai-linkedin-avatars/ecdedios" not in photo
    assert "avatars.githubusercontent.com/ecdedios" in photo


def test_photo_broken_s3_falls_back_to_github():
    import httpx
    from extract.profile_photo import resolve_profile_photo

    profile = {
        "full_name": "Irem Ergun",
        "profile_pic_url": "https://s3.us-west-1.amazonaws.com/progai-linkedin-avatars/irem-machine-learning-engineer.png",
        "github_url": "https://github.com/irombie",
        "linkedin_url": "https://linkedin.com/in/irem-machine-learning-engineer",
    }
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        photo = resolve_profile_photo(profile, http_client=client)
    assert "avatars.githubusercontent.com/irombie" in photo


def test_photo_initials_when_no_urls():
    profile = {
        "first_name": "Analysa",
        "last_name": "Gonzales",
        "full_name": "Analysa Gonzales",
        "profile_pic_url": "",
    }
    photo = resolve_profile_photo(profile, use_initials_fallback=True, validate_urls=False)
    assert photo.startswith("https://ui-avatars.com/api/")
    assert "Analysa" in photo


if __name__ == "__main__":
    test_search_body_from_url()
    test_build_search_body()
    test_build_search_body_languages_as_list()
    test_build_search_body_female_first_name()
    test_validate_search_requires_geo()
    test_build_search_body_yo_as_list()
    test_format_api_error_validation()
    test_profile_has_emails_empty_list_string()
    test_profile_has_emails_primary()
    test_search_fallback_bodies()
    test_infer_seniority_from_text()
    test_job_queries_from_search()
    test_role_to_tab_product_and_devops()
    test_row_has_email()
    test_gmail_only_emails()
    test_profile_to_row()
    test_profile_to_row_drops_company_only()
    test_photo_initials_fallback()
    test_photo_github_fallback()
    test_progai_avatar_from_linkedin()
    test_photo_linkedin_guess_when_api_omits_pic()
    test_photo_trusts_api_url_like_getprog()
    test_photo_validate_urls_can_replace_broken_s3()
    test_photo_broken_s3_falls_back_to_github()
    test_photo_initials_when_no_urls()
    print("OK")
