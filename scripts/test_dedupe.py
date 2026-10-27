"""Tests for name/role/company/photo deduplication."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dedupe import is_same_person
from pipeline import csv_path_for_sheet_name, filter_new_candidates, sanitize_csv_stem


def test_same_person_all_four_fields():
    a = {
        "name": "Jane Doe",
        "role": "ML Engineer",
        "current_company": "Acme",
        "photo": "https://example.com/jane.png",
    }
    b = {**a, "email": "other@email.com"}
    assert is_same_person(a, b)


def test_different_role_is_new_person():
    a = {"name": "Jane Doe", "role": "ML Engineer", "current_company": "Acme", "photo": "https://x.com/a.png"}
    b = {"name": "Jane Doe", "role": "Staff Engineer", "current_company": "Acme", "photo": "https://x.com/a.png"}
    assert not is_same_person(a, b)


def test_same_linkedin_url_different_photo():
    a = {
        "name": "Jane Doe",
        "role": "ML Engineer",
        "current_company": "Acme",
        "photo": "",
        "linkedin_url": "https://linkedin.com/in/jane-doe",
    }
    b = {**a, "photo": "https://ui-avatars.com/api/?name=Jane"}
    assert is_same_person(a, b)


def test_filter_checks_one_by_one():
    import pipeline as pl

    existing = [
        {
            "name": "In CSV",
            "role": "Engineer",
            "current_company": "Corp",
            "photo": "https://example.com/in.png",
        }
    ]
    original = pl._load_existing_csv
    pl._load_existing_csv = lambda csv_path=None: list(existing)
    try:
        candidates = [
            existing[0],
            {
                "name": "New Hire",
                "role": "Engineer",
                "current_company": "Other",
                "photo": "https://example.com/new.png",
            },
        ]
        new_rows, skipped = filter_new_candidates(candidates)
        assert skipped == 1
        assert len(new_rows) == 1
        assert new_rows[0]["name"] == "New Hire"
    finally:
        pl._load_existing_csv = original


def test_csv_named_after_sheet():
    assert sanitize_csv_stem("LatAm") == "LatAm"
    assert csv_path_for_sheet_name("LatAm").name == "LatAm.csv"
    assert sanitize_csv_stem("LatAm / Brazil") == "LatAm - Brazil"
    assert csv_path_for_sheet_name(None).name == "candidates.csv"


def test_filter_uses_named_csv():
    import csv as csvmod
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        csv_file = Path(tmp) / "LatAm.csv"
        with csv_file.open("w", newline="", encoding="utf-8") as f:
            w = csvmod.DictWriter(f, fieldnames=["name", "role", "current_company", "photo"])
            w.writeheader()
            w.writerow(
                {
                    "name": "In CSV",
                    "role": "Engineer",
                    "current_company": "Corp",
                    "photo": "https://example.com/in.png",
                }
            )
        new_rows, skipped = filter_new_candidates(
            [
                {
                    "name": "In CSV",
                    "role": "Engineer",
                    "current_company": "Corp",
                    "photo": "https://example.com/in.png",
                },
                {
                    "name": "New Hire",
                    "role": "Engineer",
                    "current_company": "Other",
                    "photo": "https://example.com/new.png",
                },
            ],
            csv_path=csv_file,
        )
        assert skipped == 1
        assert len(new_rows) == 1
        assert new_rows[0]["name"] == "New Hire"


def test_clear_csv_only_deletes_matching_sheet_file():
    import tempfile
    import pipeline as pl

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        latam = data / "LatAm.csv"
        us = data / "US.csv"
        leftover = data / "candidates.csv"
        latam.write_text("name\nA\n", encoding="utf-8")
        us.write_text("name\nB\n", encoding="utf-8")
        leftover.write_text("name\nC\n", encoding="utf-8")

        original_dir = pl.DATA_DIR
        original_fetch = pl.fetch_sheet_name
        original_cached = pl.cached_spreadsheet_name
        pl.DATA_DIR = data
        pl.fetch_sheet_name = lambda settings=None, log_fn=None: "LatAm"
        pl.cached_spreadsheet_name = lambda settings=None: "LatAm"
        try:
            path, deleted = pl.clear_csv({"google_sheet_url": "x"})
            assert deleted is True
            assert path.name == "LatAm.csv"
            assert not latam.exists()
            assert us.exists()
            assert leftover.exists()
        finally:
            pl.DATA_DIR = original_dir
            pl.fetch_sheet_name = original_fetch
            pl.cached_spreadsheet_name = original_cached


if __name__ == "__main__":
    test_same_person_all_four_fields()
    test_different_role_is_new_person()
    test_same_linkedin_url_different_photo()
    test_filter_checks_one_by_one()
    test_csv_named_after_sheet()
    test_filter_uses_named_csv()
    test_clear_csv_only_deletes_matching_sheet_file()
    print("OK")
