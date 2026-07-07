"""Transport layer for the Washington State Legislature SOAP/XML web services.

Every .asmx method also answers a plain HTTP GET with query-string parameters and
returns the same XML a SOAP call would (see section 14 of the API reference). We use
that REST-style GET here because it is the simplest thing that works from Python with
no external dependencies.

Two transports implement the same tiny contract -- ``get(service, method, params)``
returns an XML string:

* :class:`HttpSoapClient` -- calls the live service over HTTPS.
* :class:`FixtureClient`  -- reads canned XML from a directory of fixture files.

The fixture client lets the whole pipeline run and be tested with no network access.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Protocol

# Per-service endpoint bases. Every method we call lives under one of these.
BASE_URL = "https://wslwebservices.leg.wa.gov"

SERVICE_BASES: Dict[str, str] = {
    "LegislationService": f"{BASE_URL}/LegislationService.asmx",
    "CommitteeActionService": f"{BASE_URL}/CommitteeActionService.asmx",
}


class SoapClient(Protocol):
    """Minimal transport contract shared by the live and fixture clients."""

    def get(self, service: str, method: str, params: Dict[str, object]) -> str:
        ...


class HttpSoapClient:
    """Calls the live WA Legislature services over HTTPS via REST-style GET.

    The Legislature publishes no rate limit and no performance SLA, so we add a
    couple of retries with backoff and a sane timeout rather than hammering it.
    """

    def __init__(self, timeout: float = 30.0, retries: int = 2, backoff: float = 2.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get(self, service: str, method: str, params: Dict[str, object]) -> str:
        base = SERVICE_BASES.get(service)
        if base is None:
            raise ValueError(f"Unknown service {service!r}")

        query = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
        url = f"{base}/{method}?{query}"

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "wa-leg-history/1.0"}
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                # A SOAP fault comes back as HTTP 500 with an explanatory body
                # (see section 14). Surface the body -- it names the bad param.
                body = exc.read().decode("utf-8", errors="replace")
                raise SoapFault(
                    f"{method} returned HTTP {exc.code}: {body[:500]}"
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * (2**attempt))
                    continue
                raise

        # Unreachable, but keeps type-checkers happy.
        raise RuntimeError(str(last_error))


class FixtureClient:
    """Serves canned XML from a directory -- used for offline runs and tests.

    Looks for ``<method>.xml`` in ``fixture_dir`` (e.g. ``GetLegislation.xml``).
    The service name is ignored because method names are unique across the two
    services we touch.
    """

    def __init__(self, fixture_dir: str):
        self.fixture_dir = fixture_dir

    def get(self, service: str, method: str, params: Dict[str, object]) -> str:
        path = os.path.join(self.fixture_dir, f"{method}.xml")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No fixture for {method} at {path}")
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()


class SoapFault(Exception):
    """Raised when a service returns a SOAP fault (HTTP 500 with a message body)."""
