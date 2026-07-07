"""wa_leg_history -- build a chronological JSON timeline of a WA State bill.

Public API:
    build_bill_history_timeline(biennium, bill_number, client=None)
    HttpSoapClient   -- live HTTPS transport
    FixtureClient    -- offline transport backed by sample XML files
"""

from .client import FixtureClient, HttpSoapClient, SoapFault
from .timeline import build_bill_history_timeline

__all__ = [
    "build_bill_history_timeline",
    "HttpSoapClient",
    "FixtureClient",
    "SoapFault",
]

__version__ = "1.0.0"
