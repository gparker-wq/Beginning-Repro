"""Parse WA Legislature XML responses into plain Python dicts.

The services return XML in the ``http://WSLWebServices.leg.wa.gov/`` default
namespace. Rather than hard-code that namespace (the contract dates to 2006 and
we cannot confirm every element name against a live call in this environment),
we match elements by *local name* and ignore the namespace. That keeps the
parser working even if a namespace prefix or URI shifts.

Each ``parse_*`` function returns either a header dict or a list of normalized
timeline events. A normalized event is::

    {
        "date":     "2025-01-20T10:00:00",   # raw date string from the service (may be None)
        "category": "committee_referral",     # one of the four event kinds
        "title":    "Referred to Transportation",
        "detail":   { ... category-specific fields ... },
    }
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional


def _local(tag: str) -> str:
    """Strip any ``{namespace}`` prefix from an element tag."""
    return tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, name: str) -> Optional[ET.Element]:
    """First descendant (any depth) whose local name matches ``name``."""
    for child in element.iter():
        if _local(child.tag) == name:
            return child
    return None


def _text(element: Optional[ET.Element], name: str) -> Optional[str]:
    """Text of the first direct-or-descendant child named ``name``, trimmed."""
    if element is None:
        return None
    for child in element.iter():
        if _local(child.tag) == name and child is not element:
            return (child.text or "").strip() or None
    return None


def _iter_named(root: ET.Element, name: str):
    """Yield every element in the tree whose local name matches ``name``."""
    for element in root.iter():
        if _local(element.tag) == name:
            yield element


# --------------------------------------------------------------------------- #
# Header parsers (steps 1-2 of the recipe)
# --------------------------------------------------------------------------- #

def parse_legislation(xml: str) -> Dict[str, Optional[str]]:
    """GetLegislation -> the bill's core record (title, type, sponsor, ...)."""
    root = ET.fromstring(xml)
    leg = _find(root, "Legislation")
    if leg is None:
        return {}
    return {
        "bill_id": _text(leg, "BillId"),
        "bill_number": _text(leg, "BillNumber"),
        "biennium": _text(leg, "Biennium"),
        "short_description": _text(leg, "ShortDescription"),
        "long_description": _text(leg, "LongDescription"),
        "legislation_type": _text(leg, "LongLegislationType")
        or _text(leg, "ShortLegislationType"),
        "sponsor": _text(leg, "Sponsor"),
        "prime_sponsor_id": _text(leg, "PrimeSponsorID"),
        "companion": _text(leg, "CompanionBillId") or _text(leg, "Companions"),
        "current_version": _text(leg, "CurrentVersion")
        or _text(leg, "SubstituteVersion"),
        "introduced_date": _text(leg, "IntroducedDate"),
    }


def parse_current_status(xml: str) -> Dict[str, Optional[str]]:
    """GetCurrentStatus -> where the bill is right now."""
    root = ET.fromstring(xml)
    status = _find(root, "LegislativeStatus") or root
    return {
        "status": _text(status, "Status"),
        "history_line": _text(status, "HistoryLine"),
        "action_date": _text(status, "ActionDate"),
        "amended_by_opposite_body": _text(status, "AmendedByOppositeBody"),
        "partial_veto": _text(status, "PartialVeto"),
        "veto": _text(status, "Veto"),
        "amendments_exist": _text(status, "AmendmentsExist"),
    }


# --------------------------------------------------------------------------- #
# Timeline-event parsers (steps 3-7 of the recipe)
# --------------------------------------------------------------------------- #

def parse_committee_referrals(xml: str) -> List[Dict]:
    """GetCommitteeReferralsByBill -> which committees received the bill, when."""
    root = ET.fromstring(xml)
    events: List[Dict] = []
    for referral in _iter_named(root, "CommitteeReferral"):
        agency = _text(referral, "Agency")
        committee = _text(referral, "CommitteeName") or _text(referral, "Name")
        date = _text(referral, "ReferralDate") or _text(referral, "Date")
        where = " ".join(part for part in (agency, committee) if part)
        events.append(
            {
                "date": date,
                "category": "committee_referral",
                "title": f"Referred to {where}".strip(),
                "detail": {"agency": agency, "committee": committee},
            }
        )
    return events


def parse_hearings(xml: str) -> List[Dict]:
    """GetHearings -> scheduled hearing events."""
    root = ET.fromstring(xml)
    events: List[Dict] = []
    for hearing in _iter_named(root, "Hearing"):
        # Hearing details are typically nested under a CommitteeMeeting element.
        meeting = _find(hearing, "CommitteeMeeting") or hearing
        date = _text(meeting, "Date") or _text(hearing, "Date")
        committee = _text(meeting, "CommitteeName") or _text(meeting, "Committees")
        agency = _text(meeting, "Agency")
        location = _text(meeting, "Room") or _text(meeting, "Location")
        where = " ".join(part for part in (agency, committee) if part)
        events.append(
            {
                "date": date,
                "category": "hearing",
                "title": f"Hearing scheduled: {where}".strip().rstrip(":"),
                "detail": {
                    "agency": agency,
                    "committee": committee,
                    "location": location,
                },
            }
        )
    return events


def parse_roll_calls(xml: str) -> List[Dict]:
    """GetRollCalls -> each floor roll call with vote tallies."""
    root = ET.fromstring(xml)
    events: List[Dict] = []
    for roll in _iter_named(root, "RollCall"):
        agency = _text(roll, "Agency")
        motion = _text(roll, "Motion")
        date = _text(roll, "VoteDate") or _text(roll, "Date")
        yeas = _vote_count(roll, "YeaVotes") or _count_votes(roll, "Yea")
        nays = _vote_count(roll, "NayVotes") or _count_votes(roll, "Nay")
        events.append(
            {
                "date": date,
                "category": "roll_call",
                "title": f"{agency} floor vote: {motion}".strip(),
                "detail": {
                    "agency": agency,
                    "motion": motion,
                    "yeas": yeas,
                    "nays": nays,
                },
            }
        )
    return events


def _vote_count(roll: ET.Element, tally_name: str) -> Optional[str]:
    """Read a tally like ``<YeaVotes><Count>71</Count></YeaVotes>``.

    Handles both the nested ``Count`` form and a flat ``<YeaVotes>71</YeaVotes>``.
    """
    tally = _find(roll, tally_name)
    if tally is None:
        return None
    count = _text(tally, "Count")
    if count:
        return count
    return (tally.text or "").strip() or None


def _count_votes(roll: ET.Element, vote_value: str) -> Optional[str]:
    """Fallback tally: count member <Vote> entries whose value matches."""
    count = 0
    found_any = False
    for vote in _iter_named(roll, "Vote"):
        found_any = True
        if (_text(vote, "VOte") or _text(vote, "Vote") or "").lower() == vote_value.lower():
            count += 1
    return str(count) if found_any else None


def parse_amendments(xml: str) -> List[Dict]:
    """GetAmendmentsForBiennium -> amendments offered on the bill."""
    root = ET.fromstring(xml)
    events: List[Dict] = []
    for amendment in _iter_named(root, "Amendment"):
        name = _text(amendment, "Name")
        agency = _text(amendment, "Agency")
        action = _text(amendment, "FloorAction")
        date = _text(amendment, "FloorActionDate") or _text(amendment, "Date")
        sponsor = _text(amendment, "SponsorName") or _text(amendment, "Sponsor")
        events.append(
            {
                "date": date,
                "category": "amendment",
                "title": f"Amendment {name} ({action})".strip(),
                "detail": {
                    "name": name,
                    "agency": agency,
                    "sponsor": sponsor,
                    "floor_action": action,
                    "document_url": _text(amendment, "HtmUrl")
                    or _text(amendment, "PdfUrl"),
                },
            }
        )
    return events
