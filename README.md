# wa-leg-history

Build a single **chronological JSON timeline** of a Washington State Legislature
bill's history from the WA Legislature SOAP/XML web services
(`wslwebservices.leg.wa.gov`).

Given a biennium and bill number, the tool calls the services in the order laid
out in the [WA Legislature Data & API Reference](#) and merges the results into
one date-sorted history — the same shape whether a bill died in committee or
became law.

## ⚠️ This was built and tested against SAMPLE data

The environment this was developed in **cannot reach `wslwebservices.leg.wa.gov`**
(the outbound proxy denies it with HTTP 403 — an organization egress-policy
block, not a service outage). So the pipeline was exercised against **reconstructed
sample XML fixtures** in [`tests/fixtures/`](tests/fixtures/), modeled on the
expected response shapes — **not** live responses.

The assembly and sorting logic is proven. The **exact field names the parser
looks for are unverified against a live call** and should be confirmed before you
rely on this in production. See [Verifying against live data](#verifying-against-live-data).

## What it does

For `biennium` + `billNumber` it calls, in order:

| Step | Service.Method | Role |
|------|----------------|------|
| Header | `LegislationService.GetLegislation` | title, type, sponsor, companion |
| Header | `LegislationService.GetCurrentStatus` | where the bill is now |
| Event | `CommitteeActionService.GetCommitteeReferralsByBill` | committee referrals |
| Event | `LegislationService.GetHearings` | scheduled hearings |
| Event | `LegislationService.GetRollCalls` | floor votes |
| Event | `LegislationService.GetAmendmentsForBiennium` | amendments offered |

The four event calls are normalized into `{date, category, title, detail}`
records, merged, and **sorted ascending by date**. Undated events sort last.

Output is a dict (JSON-serializable) with `bill`, `header`, `current_status`,
`timeline`, and a `meta` block that records the data source.

## Install

Core needs only the Python standard library (3.11+). To run the tests:

```bash
pip install -e ".[test]"
```

## Usage

### Command line

```bash
# Offline, against the bundled sample fixtures:
python -m wa_leg_history --biennium 2025-26 --bill 2137 --fixtures tests/fixtures

# Live (needs outbound access to wslwebservices.leg.wa.gov):
python -m wa_leg_history --biennium 2025-26 --bill 2137
```

`meta.data_source_note` in the output tells you which path produced the JSON, so
sample runs are never mistaken for live ones.

### As a library

```python
from wa_leg_history import build_bill_history_timeline, HttpSoapClient, FixtureClient

# Live:
timeline = build_bill_history_timeline("2025-26", 2137)

# Offline / testable:
timeline = build_bill_history_timeline(
    "2025-26", 2137, client=FixtureClient("tests/fixtures")
)
```

## Design

- **`client.py`** — transport. `HttpSoapClient` calls the live `.asmx` methods via
  their REST-style HTTP GET (returns the same XML as SOAP, per §14 of the
  reference) with retries/backoff. `FixtureClient` reads `<Method>.xml` from a
  directory so everything runs offline. Both satisfy one tiny `get()` contract,
  so the timeline builder never knows which it's using.
- **`parsers.py`** — XML → dicts. Matches elements by **local name** and ignores
  the XML namespace, so it survives namespace/prefix drift in a 2006-era contract.
- **`timeline.py`** — `build_bill_history_timeline()`: fetch, normalize, sort.
- **`cli.py`** — argument parsing and JSON output.

## Verifying against live data

When you have an environment that can reach the service:

1. Run without `--fixtures` and confirm each call returns XML (not a SOAP fault).
2. Compare live element names against those the parser looks for in
   `parsers.py` (e.g. `BillId`, `ReferralDate`, `VoteDate`, `FloorActionDate`).
   Adjust the `_text(...)` lookups if any differ.
3. Re-save real responses over the files in `tests/fixtures/` to turn them into
   genuine regression fixtures.

Fields marked uncertain in the reference (e.g. the exact committee-referral date
element) are the most likely to need adjustment.

## Tests

```bash
python -m pytest -q
```

Eight tests cover header extraction, all four event categories, ascending date
sort, the nested vote-tally shape, and undated-event ordering — all against the
sample fixtures.
