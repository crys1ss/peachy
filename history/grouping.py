"""Pure conversation grouping function for Peachy sidebar and history views."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional, Tuple


def _parse_datetime(val: Any) -> Optional[datetime]:
    """Parse a datetime instance or ISO/SQL timestamp string."""
    if isinstance(val, datetime):
        return val
    if not val or not isinstance(val, str):
        return None
    cleaned = val.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def group_conversations(
    rows: Iterable[dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Tuple[str, List[dict[str, Any]]]]:
    """Group conversations into standard chronological sections.

    Section order:
    1. "Pinned" (items with pinned=True / 1)
    2. "Today" (today 00:00:00 to now)
    3. "Yesterday" (yesterday 00:00:00 to today 00:00:00)
    4. "Previous 7 days" (7 days prior up to yesterday 00:00:00)
    5. "Previous 30 days" (30 days prior up to 7 days prior)
    6. Month buckets: "<MonthName> <Year>" (e.g. "October 2026"), newest month first.

    Rules:
    - Pinned items always go to "Pinned" only, never into date buckets.
    - Only non-empty buckets are included in the returned list.
    - Rows within each bucket maintain their original ordering.
    - Pure function: no external I/O or state modification.
    """
    if now is None:
        now = datetime.now()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    seven_days_ago = today_start - timedelta(days=7)
    thirty_days_ago = today_start - timedelta(days=30)

    pinned_items: List[dict[str, Any]] = []
    today_items: List[dict[str, Any]] = []
    yesterday_items: List[dict[str, Any]] = []
    prev_7_days_items: List[dict[str, Any]] = []
    prev_30_days_items: List[dict[str, Any]] = []
    month_buckets: dict[Tuple[int, int, str], List[dict[str, Any]]] = {}
    earlier_items: List[dict[str, Any]] = []

    for row in rows:
        if bool(row.get("pinned", False)):
            pinned_items.append(row)
            continue

        raw_ts = row.get("updated_at") or row.get("created_at")
        dt = _parse_datetime(raw_ts)

        if dt is None:
            earlier_items.append(row)
        elif dt >= today_start:
            today_items.append(row)
        elif dt >= yesterday_start:
            yesterday_items.append(row)
        elif dt >= seven_days_ago:
            prev_7_days_items.append(row)
        elif dt >= thirty_days_ago:
            prev_30_days_items.append(row)
        else:
            month_key = (dt.year, dt.month, dt.strftime("%B %Y"))
            month_buckets.setdefault(month_key, []).append(row)

    result: List[Tuple[str, List[dict[str, Any]]]] = []

    if pinned_items:
        result.append(("Pinned", pinned_items))
    if today_items:
        result.append(("Today", today_items))
    if yesterday_items:
        result.append(("Yesterday", yesterday_items))
    if prev_7_days_items:
        result.append(("Previous 7 days", prev_7_days_items))
    if prev_30_days_items:
        result.append(("Previous 30 days", prev_30_days_items))

    # Sort month buckets descending by year and month
    for (year, month, label), items in sorted(month_buckets.items(), key=lambda k: (k[0][0], k[0][1]), reverse=True):
        if items:
            result.append((label, items))

    if earlier_items:
        result.append(("Earlier", earlier_items))

    return result
