"""Genuine public fixtures: provenance is recorded and every expected source value is what the file prints."""
import hashlib
import json

import pytest

from bean_api.general_research.admission import parse
from bean_api.general_research.citations import PageText, locate, separators_for
from general_research_support import FIXTURES

MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = {entry["file"]: entry for entry in MANIFEST["fixtures"]}


def test_manifest_covers_every_fixture_with_provenance():
    files = {path.name for path in FIXTURES.iterdir() if path.name != "manifest.json"}
    assert files == set(ENTRIES)
    for entry in MANIFEST["fixtures"]:
        source = entry["source"]
        assert source["url"].startswith("https://") and source["publisher"] and source["rights"]
        assert entry["data_origin"] in {"real_observation", "public_source"}
        assert entry["modifications"] == "none" or source["original_sha256"] != entry["sha256"] or \
            entry["file"].startswith("naca")
        data = (FIXTURES / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) <= 5 * 1024 * 1024


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_fixture_parses_to_its_printed_values(name):
    entry = ENTRIES[name]
    parsed = parse((FIXTURES / name).read_bytes(), entry["media_type"])
    expected, summary = entry["expected"], parsed.summary
    if summary["kind"] == "table":
        assert summary["row_count"] == expected["row_count"]
        for key in ("comment_lines", "title_lines", "format_row_line"):
            if key in expected:
                assert summary[key] == expected[key]
        names = [column["name"] for column in summary["columns"]]
        if "header" in expected:
            assert names == expected["header"]
        if "columns" in expected:
            assert [[c["name"], c["unit"]] for c in summary["columns"]] == expected["columns"]
            assert all(c["unit_status"] == "unresolved" for c in summary["columns"] if c["unit"] is None)
        text = parsed.text_pages[0]["text"].splitlines()
        for cell in expected["cells"]:
            line = text[cell["line"] - 1]
            delimiter = summary["delimiter"]
            assert line.split(delimiter)[:len(cell["values"])] == cell["values"]
    elif summary["kind"] == "json":
        table, = [t for t in summary["tables"] if t["json_path"] == expected["json_path"]]
        assert table["row_count"] == expected["row_count"]
        names = [column["name"] for column in table["columns"]]
        first = dict(zip(names, table["preview_rows"][0]["cells"]))
        assert {key: first[key] for key in expected["first_cells"]} == expected["first_cells"]
    elif summary["kind"] == "text":
        assert summary["line_count"] == expected["line_count"]
    elif summary["kind"] == "image":
        assert (summary["width"], summary["height"], summary["mode"]) == (expected["width"], expected["height"],
                                                                          expected["mode"])
    else:
        assert summary["page_count"] == expected["page_count"]
        assert [page["text_layer"] for page in parsed.pages] == expected["text_layers"]
        if "active_content" in expected:
            assert parsed.active_content == expected["active_content"]
    pages = [PageText(page["text"], page["char_boxes"], page["quality"]) for page in parsed.text_pages]
    separators = separators_for(entry["media_type"], summary.get("delimiter"))
    for citation in entry["citations"]:
        found = locate(pages, citation["page_index"], citation["quote"], separators)
        assert found["status"] == citation["status"], citation
        if found["status"] == "verified" and entry["media_type"] == "application/pdf":
            assert found["bbox_e4"] is not None
