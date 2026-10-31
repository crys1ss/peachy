"""Tests for pure conversation grouping function."""

from __future__ import annotations

from datetime import datetime, timedelta
from history.grouping import group_conversations


def test_empty_list_returns_empty():
    """Empty list returns an empty list of sections."""
    assert group_conversations([], now=datetime(2026, 10, 31, 12, 0)) == []


def test_pinned_takes_precedence_over_date_buckets():
    """Pinned rows always go to 'Pinned' only, never duplicate into Today or other buckets."""
    now = datetime(2026, 10, 31, 15, 0, 0)

    rows = [
        {"id": 1, "title": "Pinned Today Chat", "pinned": True, "updated_at": "2026-10-31 14:00:00.000"},
        {"id": 2, "title": "Unpinned Today Chat", "pinned": False, "updated_at": "2026-10-31 13:00:00.000"},
        {"id": 3, "title": "Pinned Yesterday Chat", "pinned": 1, "updated_at": "2026-10-30 20:00:00.000"},
    ]

    grouped = group_conversations(rows, now=now)
    sections = [g[0] for g in grouped]

    assert sections == ["Pinned", "Today"]
    pinned_group = next(items for label, items in grouped if label == "Pinned")
    assert [r["id"] for r in pinned_group] == [1, 3]

    today_group = next(items for label, items in grouped if label == "Today")
    assert [r["id"] for r in today_group] == [2]


def test_midnight_boundary():
    """Exact midnight boundary cleanly separates Today (>= 00:00:00) and Yesterday (< 00:00:00)."""
    now = datetime(2026, 10, 31, 0, 5, 0)  # 5 minutes past midnight

    rows = [
        {"id": 1, "title": "Just After Midnight", "updated_at": "2026-10-31 00:00:01.000"},
        {"id": 2, "title": "Exact Midnight", "updated_at": "2026-10-31 00:00:00.000"},
        {"id": 3, "title": "One Second Before Midnight", "updated_at": "2026-10-30 23:59:59.000"},
    ]

    grouped = group_conversations(rows, now=now)
    labels = [g[0] for g in grouped]

    assert labels == ["Today", "Yesterday"]
    today_items = next(items for label, items in grouped if label == "Today")
    assert [r["id"] for r in today_items] == [1, 2]

    yesterday_items = next(items for label, items in grouped if label == "Yesterday")
    assert [r["id"] for r in yesterday_items] == [3]


def test_month_rollover_at_first_of_month():
    """When now is the 1st of a new month, yesterday correctly groups the last day of the prior month."""
    now = datetime(2026, 11, 1, 10, 0, 0)

    rows = [
        {"id": 1, "title": "First of November", "updated_at": "2026-11-01 09:00:00.000"},
        {"id": 2, "title": "Halloween Night", "updated_at": "2026-10-31 22:00:00.000"},
        {"id": 3, "title": "Five Days Prior", "updated_at": "2026-10-27 12:00:00.000"},
        {"id": 4, "title": "Twenty Days Prior", "updated_at": "2026-10-12 12:00:00.000"},
        {"id": 5, "title": "Mid September", "updated_at": "2026-09-15 12:00:00.000"},
    ]

    grouped = group_conversations(rows, now=now)
    labels = [g[0] for g in grouped]

    assert labels == [
        "Today",
        "Yesterday",
        "Previous 7 days",
        "Previous 30 days",
        "September 2026",
    ]

    today_items = next(items for l, items in grouped if l == "Today")
    assert [r["id"] for r in today_items] == [1]

    yesterday_items = next(items for l, items in grouped if l == "Yesterday")
    assert [r["id"] for r in yesterday_items] == [2]

    p7_items = next(items for l, items in grouped if l == "Previous 7 days")
    assert [r["id"] for r in p7_items] == [3]

    p30_items = next(items for l, items in grouped if l == "Previous 30 days")
    assert [r["id"] for r in p30_items] == [4]

    sep_items = next(items for l, items in grouped if l == "September 2026")
    assert [r["id"] for r in sep_items] == [5]


def test_multiple_month_buckets_ordered_descending():
    """Month buckets older than 30 days appear in descending chronological order."""
    now = datetime(2026, 10, 31, 12, 0, 0)

    rows = [
        {"id": 1, "title": "August Task", "updated_at": "2026-08-15 10:00:00.000"},
        {"id": 2, "title": "July Task", "updated_at": "2026-07-20 10:00:00.000"},
        {"id": 3, "title": "June Task", "updated_at": "2026-06-05 10:00:00.000"},
    ]

    grouped = group_conversations(rows, now=now)
    labels = [g[0] for g in grouped]

    assert labels == ["August 2026", "July 2026", "June 2026"]
    assert [r["id"] for r in grouped[0][1]] == [1]
    assert [r["id"] for r in grouped[1][1]] == [2]
    assert [r["id"] for r in grouped[2][1]] == [3]


def test_non_empty_buckets_only():
    """Empty buckets are omitted from the output list."""
    now = datetime(2026, 10, 31, 12, 0, 0)

    rows = [
        {"id": 1, "title": "Yesterday Task", "updated_at": "2026-10-30 10:00:00.000"}
    ]

    grouped = group_conversations(rows, now=now)
    assert len(grouped) == 1
    assert grouped[0][0] == "Yesterday"
    assert grouped[0][1][0]["id"] == 1
