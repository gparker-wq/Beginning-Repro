"""Tests for the bill-history timeline, run against the bundled sample fixtures.

These prove the assembly and sorting logic end-to-end without any network
access. They do NOT prove the parser matches the live service's exact field
names -- that requires a live call (see README, "Verifying against live data").
"""

import os

import pytest

from wa_leg_history import FixtureClient, build_bill_history_timeline

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def result():
    client = FixtureClient(FIXTURE_DIR)
    return build_bill_history_timeline("2025-26", 2137, client=client)


def test_header_is_populated(result):
    assert result["bill"]["bill_id"] == "HB 2137"
    assert result["bill"]["bill_number"] == 2137
    assert result["header"]["legislation_type"] == "Bill"
    assert "civic" in result["header"]["long_description"].lower()


def test_current_status_is_populated(result):
    assert result["current_status"]["status"] == "In Senate Committee"
    assert result["current_status"]["amendments_exist"] == "true"


def test_all_four_event_categories_present(result):
    assert set(result["meta"]["categories"]) == {
        "amendment",
        "committee_referral",
        "hearing",
        "roll_call",
    }


def test_events_are_sorted_ascending_by_date(result):
    from wa_leg_history.timeline import _sort_key

    keys = [_sort_key(event) for event in result["timeline"]]
    assert keys == sorted(keys)


def test_first_event_is_the_house_referral(result):
    first = result["timeline"][0]
    assert first["category"] == "committee_referral"
    assert first["date"].startswith("2025-01-13")


def test_roll_call_tally_read_from_nested_count(result):
    roll_calls = [e for e in result["timeline"] if e["category"] == "roll_call"]
    assert roll_calls[0]["detail"]["yeas"] == "71"
    assert roll_calls[0]["detail"]["nays"] == "25"


def test_amendment_carries_document_url(result):
    amendments = [e for e in result["timeline"] if e["category"] == "amendment"]
    assert amendments[0]["detail"]["document_url"].startswith("https://")


def test_undated_events_sort_last():
    from wa_leg_history.timeline import _sort_key

    dated = _sort_key({"date": "2025-01-01T00:00:00"})
    undated = _sort_key({"date": None})
    assert dated < undated
