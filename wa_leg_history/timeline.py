"""Assemble a single chronological JSON timeline of a WA bill's history.

This is the heart of the tool. It follows the order in section 15 of the API
reference:

    Header  : GetLegislation  +  GetCurrentStatus
    Events  : GetCommitteeReferralsByBill
              GetHearings
              GetRollCalls
              GetAmendmentsForBiennium

The event-producing calls are merged into one list and sorted ascending by
date, giving a single chronology that reads the same whether the bill died in
committee or became law.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import parsers
from .client import HttpSoapClient, SoapClient


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse a WA service date string into a datetime, or None if unparseable.

    The services emit ISO-8601-ish strings such as ``2025-01-15T00:00:00`` or
    ``2025-01-20T10:00:00-08:00``. ``datetime.fromisoformat`` handles both on
    Python 3.11. Anything else sorts to the end of the timeline.
    """
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        # Trailing 'Z' (UTC) is not accepted before 3.11's full support; retry.
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None


def _sort_key(event: Dict):
    """Sort events ascending by date; undated events sort last, stably.

    Naive and timezone-aware datetimes cannot be compared directly, so we
    normalize everything to UTC for the comparison only (the displayed ``date``
    field keeps its original string untouched).
    """
    parsed = _parse_date(event.get("date"))
    if parsed is None:
        return (1, datetime.max.replace(tzinfo=timezone.utc))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return (0, parsed)


def build_bill_history_timeline(
    biennium: str,
    bill_number: int,
    client: Optional[SoapClient] = None,
) -> Dict:
    """Build a normalized, chronological history timeline for one bill.

    Args:
        biennium: Two-year cycle string, e.g. ``"2025-26"``.
        bill_number: Numeric bill number, e.g. ``2137``.
        client: Transport to use. Defaults to the live :class:`HttpSoapClient`.
            Pass a :class:`FixtureClient` to run offline against sample XML.

    Returns:
        A dict with ``bill``, ``header``, ``current_status``, ``timeline``
        (date-sorted events), and a ``meta`` block. Ready for ``json.dumps``.
    """
    if client is None:
        client = HttpSoapClient()

    params = {"biennium": biennium, "billNumber": bill_number}

    # --- Header: steps 1-2 --------------------------------------------------
    legislation = parsers.parse_legislation(
        client.get("LegislationService", "GetLegislation", params)
    )
    current_status = parsers.parse_current_status(
        client.get("LegislationService", "GetCurrentStatus", params)
    )

    # --- Timeline events: steps 3-7 (referrals, hearings, votes, amendments) -
    events: List[Dict] = []
    events += parsers.parse_committee_referrals(
        client.get("CommitteeActionService", "GetCommitteeReferralsByBill", params)
    )
    events += parsers.parse_hearings(
        client.get("LegislationService", "GetHearings", params)
    )
    events += parsers.parse_roll_calls(
        client.get("LegislationService", "GetRollCalls", params)
    )
    events += parsers.parse_amendments(
        client.get("LegislationService", "GetAmendmentsForBiennium", params)
    )

    events.sort(key=_sort_key)

    bill_id = legislation.get("bill_id") or f"HB {bill_number}"

    return {
        "bill": {
            "biennium": biennium,
            "bill_number": bill_number,
            "bill_id": bill_id,
        },
        "header": legislation,
        "current_status": current_status,
        "timeline": events,
        "meta": {
            "event_count": len(events),
            "categories": sorted({event["category"] for event in events}),
            "source": "wslwebservices.leg.wa.gov (SOAP/XML web services)",
        },
    }
