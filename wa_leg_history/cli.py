"""Command-line entry point for the bill-history timeline tool.

Examples:
    # Live (requires outbound access to wslwebservices.leg.wa.gov):
    python -m wa_leg_history --biennium 2025-26 --bill 2137

    # Offline, against the bundled sample fixtures:
    python -m wa_leg_history --biennium 2025-26 --bill 2137 \
        --fixtures tests/fixtures
"""

from __future__ import annotations

import argparse
import json
import sys

from .client import FixtureClient, HttpSoapClient, SoapFault
from .timeline import build_bill_history_timeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="wa_leg_history",
        description="Build a chronological JSON timeline of a WA State bill's history.",
    )
    parser.add_argument("--biennium", default="2025-26", help='e.g. "2025-26"')
    parser.add_argument("--bill", type=int, default=2137, help="numeric bill number, e.g. 2137")
    parser.add_argument(
        "--fixtures",
        metavar="DIR",
        help="read sample XML from DIR instead of calling the live service",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="live HTTP timeout (s)")
    args = parser.parse_args(argv)

    if args.fixtures:
        client = FixtureClient(args.fixtures)
        source_note = f"SAMPLE DATA from {args.fixtures} (not live)"
    else:
        client = HttpSoapClient(timeout=args.timeout)
        source_note = "live wslwebservices.leg.wa.gov"

    try:
        result = build_bill_history_timeline(args.biennium, args.bill, client=client)
    except SoapFault as exc:
        print(f"SOAP fault from service: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 -- CLI boundary, report cleanly
        print(f"Error building timeline ({source_note}): {exc}", file=sys.stderr)
        return 1

    result.setdefault("meta", {})["data_source_note"] = source_note
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
