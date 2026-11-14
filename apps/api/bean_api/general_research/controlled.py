"""A deterministic controlled responder for browser development and tests without Gemini.

It restates the first meaningful line of each text page and the first rows of
delimited tables, with exact quotations, so the full request, citation and record
path can be exercised offline. It does not interpret anything. Records produced
with it are labelled ``controlled`` and never count as live Gemini output.
Enable it only explicitly (``BEAN_GENERAL_ANALYSIS_MODE=controlled_demo``).
"""
from __future__ import annotations

import csv
import io
import json

from .textformats import header_unit
from .transport import AnalysisEnvelope


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if sum(ch.isalnum() for ch in stripped) >= 3:
            return stripped[:200].rsplit(" ", 1)[0] if len(stripped) > 200 else stripped
    return None


def demo_responder(envelope: AnalysisEnvelope) -> str:
    citations, claims, tables = [], [], []
    for source in envelope.sources:
        for part in source["parts"]:
            if part["kind"] != "text":
                continue
            line = _first_line(part["text"])
            if not line:
                continue
            cid = f"C{len(citations) + 1}"
            citations.append({"id": cid, "source": source["label"], "page_index": part["page_index"], "quote": line})
            claims.append({"text": f"The first line of {source['label']} reads: {line}", "kind": "observation",
                           "uncertainty": "not_stated", "citation_ids": [cid]})
            if source["media_type"] in ("text/csv", "text/tab-separated-values") and len(tables) < 2:
                delimiter = "\t" if source["media_type"] == "text/tab-separated-values" else ","
                rows = [row for row in csv.reader(io.StringIO(part["text"]), delimiter=delimiter)
                        if row and not row[0].lstrip().startswith("#")][:6]
                if rows:
                    header, body = rows[0][:24], [row[:24] for row in rows[1:]]
                    tables.append({"title": f"First rows of {source['label']}", "source": source["label"],
                                   "page_index": part["page_index"],
                                   "columns": [{"name": name or "(unnamed)", "unit": header_unit(name)} for name in header],
                                   "rows": [[cell if cell != "" else None for cell in row] for row in body],
                                   "citation_ids": [cid], "notes": "Copied from the file without interpretation."})
    output = {
        "summary": "Controlled demonstration response generated locally without Gemini. It restates the first line "
                   "of each text source and the first table rows; it does not interpret the data.",
        "extracted_tables": tables, "claims": claims[:12],
        "limitations": ["This controlled response was produced locally for testing; it is not an analysis."],
        "clarifications": [], "citations": citations[:30],
        "suggested_next_steps": [{"text": "Review the restated values against the source files.",
                                  "rationale": "Controlled responses only restate file contents.",
                                  "kind": "review_extracted_values",
                                  "citation_ids": [citations[0]["id"]] if citations else []}]}
    return json.dumps(output, ensure_ascii=False)
