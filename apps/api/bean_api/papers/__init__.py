"""Local paper (PDF) admission helpers: bounded parsing, page previews, page subsets, manifests.

Owner 4 module. These helpers receive already-received bytes and return data. They never
receive credentials, call a model provider, decide scientific eligibility, create approvals,
persist records or submit jobs. Owner 2's routes authenticate, persist and authorize;
Owner 3's gateway consumes a selected page subset; Owner 1 decides what can be checked.

Every parse and render runs in a separate bounded process (`_pdf_worker.py`) with a minimal
environment, CPU/memory/output/time limits. That is resource isolation, not a complete
security sandbox. Document JavaScript, attachments, links and launch actions are never
executed or followed.
"""
from __future__ import annotations

from .admission import (  # noqa: F401
    PaperError, inspect_paper, render_page, select_pages, sniff_pdf,
)
from .citations import match_quotation, render_box, validate_citation  # noqa: F401
from .limits import capabilities  # noqa: F401
