"""Admission and local parsing of general research files; nothing here calls a provider.

Covers arbitrary columns and units outside pharmacokinetics, empty versus missing
values, encodings, malformed and oversized inputs, PDF hostility (bombs, nesting,
encryption, polyglots, active content), scanned pages, rotation, images and the
effective memory guard of the isolated parser.
"""
from pathlib import Path
import sys

import pytest

from bean_api.general_research import limits as L
from bean_api.general_research.admission import Refusal, canonical_media_type, parse, source_name
from bean_api.general_research.sandbox import WorkerLimitExceeded, describe_guards, run_worker
from bean_api.general_research.textformats import ParseRefused, decode_text, parse_json_document
import general_research_pdf as hostile
from general_research_support import SOIL_CSV, jpeg_bytes, paper_pdf, png_bytes, scanned_pdf


# --------------------------------------------------------------------------- tables and text
def test_arbitrary_columns_and_units_are_preserved_exactly():
    parsed = parse(SOIL_CSV, "text/csv")
    columns = {c["name"]: c for c in parsed.summary["columns"]}
    assert list(columns) == ["site_id", "depth (cm)", "moisture (%)", "nitrate [mg/kg]", "texture", "notes"]
    assert columns["depth (cm)"]["unit"] == "cm" and columns["nitrate [mg/kg]"]["unit"] == "mg/kg"
    assert columns["site_id"]["unit"] is None and columns["site_id"]["unit_status"] == "unresolved"
    assert columns["moisture (%)"]["empty_cells"] == 1            # empty value kept as empty
    assert columns["nitrate [mg/kg]"]["missing_marker_cells"] == 1  # "NA" is a written missing marker
    assert columns["nitrate [mg/kg]"]["min_as_written"] == "3.85" and columns["nitrate [mg/kg]"]["max_as_written"] == "5.10"
    first = parsed.summary["preview_rows"][0]
    assert first == {"line": 2, "cells": ["N-01", "10", "23.4", "5.10", "loam", ""]}
    assert parsed.pages[0]["page_index"] == 0 and parsed.pages[0]["page_number"] == 1
    assert parsed.text_pages[0]["text"] == SOIL_CSV.decode()        # the exact text is what gets cited


def test_short_rows_are_missing_not_empty_and_are_reported():
    parsed = parse(b"a,b,c\n1,2,3\n4,5\n", "text/csv")
    assert parsed.summary["preview_rows"][1]["cells"] == ["4", "5", None]
    assert parsed.summary["ragged_row_lines"] == [3]
    assert "rows_with_different_field_counts" in parsed.warnings


def test_tsv_semicolon_decimal_comma_and_comment_preamble():
    tsv = parse("# instrument: CTD-7\nDepth (m)\tSalinity (PSU)\n0.5\t35.1\n".encode(), "text/tab-separated-values")
    assert tsv.summary["comment_lines"] == 1 and tsv.summary["columns"][1]["unit"] == "PSU"
    semi = parse("Zeit (min);Konz. (\u00b5g/ml)\n0;1,5\n5;2,25\n".encode(), "text/csv")
    assert semi.summary["delimiter"] == ";" and semi.summary["decimal_comma_candidate"] is True
    assert semi.summary["columns"][1]["kind"] == "numeric" and semi.summary["columns"][1]["unit"] == "\u00b5g/ml"


def test_json_preserves_number_spelling_nested_records_and_non_ascii_keys():
    parsed = parse('{"readings": [{"site": "A", "pH": 7.10, "temp (\u00b0C)": 21.5}, {"site": "B", "pH": 6.98}]}'
                   .encode(), "application/json")
    table = parsed.summary["tables"][0]
    assert table["json_path"] == "$.readings" and table["row_count"] == 2
    assert table["preview_rows"][0]["cells"] == ["A", "7.10", "21.5"]        # 7.10 is not rewritten as 7.1
    assert table["preview_rows"][1]["cells"] == ["B", "6.98", None]
    assert table["columns"][2]["unit"] == "\u00b0C"


@pytest.mark.parametrize("data,code", [
    (b'{"a": ' + b"[" * 80 + b"]" * 80 + b"}", "json_nesting_limit"),
    (b'{"a": 1,}', "malformed_json"),
])
def test_json_refusals(data, code):
    with pytest.raises(Refusal) as refused:
        parse(data, "application/json")
    assert refused.value.code == code


def test_json_duplicate_keys_and_nonstandard_constants_are_reported_not_hidden():
    summary = parse_json_document('{"a": 1, "a": 2, "b": NaN}')
    assert summary["duplicate_keys"] == ["a"] and "nonstandard_json_constant" in summary["warnings"]


def test_text_decoding_is_explicit():
    assert decode_text("caf\u00e9".encode("utf-8"))[1] == "utf-8"
    assert decode_text("\ufeffhello".encode("utf-8"))[0] == "hello"
    text, encoding, warnings = decode_text("caf\u00e9 au lait".encode("cp1252"))
    assert text == "caf\u00e9 au lait" and encoding == "cp1252" and warnings == ["decoded_as_windows_1252_not_utf8"]
    assert decode_text("hello".encode("utf-16"))[0] == "hello"
    for data, code in [(b"\x00\x01\x02binary", "binary_content"), (b"   \n", "empty_text")]:
        with pytest.raises(ParseRefused) as refused:
            decode_text(data)
        assert refused.value.code == code


def test_markdown_headings():
    parsed = parse(b"# Field notes\n\nSoil was wet.\n## Site N-01\n", "text/markdown")
    assert parsed.summary["headings"] == [{"level": 1, "text": "Field notes"}, {"level": 2, "text": "Site N-01"}]


@pytest.mark.parametrize("data,declared,code,status", [
    (b"", "text/csv", "empty_file", 422),
    (b"x" * (L.MAX_ASSET_BYTES + 1), "text/plain", "file_too_large", 413),
    (png_bytes(), "application/pdf", "media_type_mismatch", 415),
    (b"%PDF-1.4\n...", "text/csv", "media_type_mismatch", 415),
    (b"PK\x03\x04 zip or xlsx", "text/csv", "media_type_mismatch", 415),
    (b"a,b\n\"unterminated,1\n", "text/csv", "malformed_table", 422),
])
def test_explicit_refusals(data, declared, code, status):
    with pytest.raises(Refusal) as refused:
        parse(data, canonical_media_type(declared)[1])
    assert (refused.value.code, refused.value.status) == (code, status)


def test_declared_media_types_and_aliases():
    assert canonical_media_type("text/csv; charset=utf-8") == ("text/csv", "text/csv")
    assert canonical_media_type("application/vnd.ms-excel")[1] == "text/csv"
    with pytest.raises(Refusal) as refused:
        canonical_media_type("application/x-msdownload")
    assert refused.value.status == 415


@pytest.mark.parametrize("header,expected", [
    ("results%20%E2%80%94%20final.csv", "results \u2014 final.csv"),
    ("../../../../etc/passwd.csv", "passwd.csv"),
    ("..\\..\\windows\\win.ini.csv", "win.ini.csv"),
    ("\u202efdp.exe", "fdp.exe"),
    ("paper%00.pdf", "paper.pdf"),
    ("", None),
    (None, None),
])
def test_source_names_are_inert_display_text(header, expected):
    assert source_name(header) == expected


def test_overlong_source_name_is_refused():
    with pytest.raises(Refusal):
        source_name("a" * (L.MAX_SOURCE_NAME_CHARS + 1))


# --------------------------------------------------------------------------- PDFs
def test_native_text_pdf_pages_text_boxes_and_page_images():
    parsed = parse(paper_pdf(), "application/pdf")
    first, second = parsed.pages
    assert (first["page_index"], first["page_number"], second["page_index"], second["page_number"]) == (0, 1, 1, 2)
    assert first["dimension_unit"] == "pt" and (first["width"], first["height"]) == ("612", "792")
    assert first["text_layer"] == "native_pdf_text" and first["image_media_type"] == "image/png"
    assert max(first["image_width"], first["image_height"]) <= L.RENDER_MAX_SIDE_PX
    assert first["image_sha256"] in parsed.blobs
    text = parsed.text_pages[0]
    assert "Peak concentration was 5380 ng/mL (SD 410) at 4.62 h." in text["text"]
    assert len(text["char_boxes"]) == 8 * len(text["text"])


def test_scanned_page_has_no_text_layer_but_keeps_its_page_image():
    parsed = parse(scanned_pdf(), "application/pdf")
    assert parsed.pages[0]["text_layer"] == "none" and parsed.pages[0]["text_sha256"] is None
    assert parsed.pages[0]["image_sha256"] in parsed.blobs
    assert parsed.summary["pages_without_text_layer"] == [0]
    assert "page_without_usable_text_layer:0" in parsed.warnings


def test_rotated_page_boxes_use_the_displayed_orientation():
    from bean_api.general_research.citations import PageText, locate
    document = hostile.Document("rotated")
    page = document.page()
    page.rotate = 90
    page.text(72, 720, "Rotated page with the measured value 42.7 kPa", size=12)
    parsed = parse(document.to_bytes(), "application/pdf")
    assert (parsed.pages[0]["width"], parsed.pages[0]["height"], parsed.pages[0]["rotation"]) == ("792", "612", 90)
    layer = parsed.text_pages[0]
    found = locate([PageText(layer["text"], layer["char_boxes"], layer["quality"])], 0, "42.7 kPa")
    x0, y0, x1, y1 = found["bbox_e4"]
    assert found["status"] == "verified" and x0 > 5000 and y1 - y0 > x1 - x0   # text now runs down the right side


HOSTILE_EXPECTED = {
    "truncated": "malformed_pdf", "password-protected": "encrypted_pdf", "pages-11": "pdf_page_limit",
    "pages-2000": "pdf_page_limit", "inflate-bomb": "pdf_decompression_limit",
    "image-dimension-bomb": "pdf_image_pixel_limit", "image-inflate-bomb": "pdf_image_pixel_limit",
    "nested-arrays": "pdf_nesting_limit", "page-tree-cycle": "malformed_pdf", "huge-xref-size": "pdf_object_limit",
    "html-polyglot": "media_type_mismatch", "png-bytes-named-pdf": "media_type_mismatch", "header-only": "malformed_pdf",
    "empty": "empty_file", "oversize-6mib": "file_too_large",
}


@pytest.mark.parametrize("name", sorted(HOSTILE_EXPECTED))
def test_hostile_pdfs_are_refused_with_named_codes(name):
    with pytest.raises(Refusal) as refused:
        parse(hostile.build(name), "application/pdf")
    assert refused.value.code == HOSTILE_EXPECTED[name]


@pytest.mark.parametrize("name,features", [
    ("javascript-openaction", {"javascript", "open_action", "additional_actions"}),
    ("launch-and-uri-actions", {"launch_action", "open_action", "uri_action"}),
    ("embedded-attachment", {"embedded_files"}),
])
def test_active_content_is_reported_and_never_executed(name, features):
    parsed = parse(hostile.build(name), "application/pdf")
    assert features <= set(parsed.active_content)
    assert "active_content_present_not_executed" in parsed.warnings
    assert parsed.summary["executes_document_scripts"] is False


def test_garbage_xref_is_recovered_or_refused_but_never_unbounded():
    try:
        parsed = parse(hostile.build("garbage-xref"), "application/pdf")
    except Refusal as refused:
        assert refused.code == "malformed_pdf"
    else:
        assert len(parsed.pages) == 1


def test_page_dimension_limit():
    document = hostile.Document("poster", size=(6000, 400))
    document.page().text(72, 200, "A very wide page", size=12)
    with pytest.raises(Refusal) as refused:
        parse(document.to_bytes(), "application/pdf")
    assert refused.value.code == "pdf_page_dimension_limit"


# --------------------------------------------------------------------------- images
def test_images_keep_original_bytes_and_derive_declared_previews():
    small = parse(png_bytes(), "image/png")
    assert small.pages[0]["image_sha256"] and small.preview_sha256 is None and small.text_pages[0]["quality"] == "none"
    large = parse(jpeg_bytes((3200, 1800)), "image/jpeg")
    assert large.summary["preview_reason"] == "downscaled_to_page_image_bound"
    preview = large.blobs[large.preview_sha256]
    assert preview.startswith(b"\xff\xd8\xff")
    rotated = parse(jpeg_bytes((80, 40), exif_orientation=6), "image/jpeg")
    assert rotated.summary["preview_reason"] == "exif_orientation_applied"
    assert (rotated.pages[0]["width"], rotated.pages[0]["height"]) == (40, 80)


def test_image_refusals():
    from PIL import Image
    import io
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="PNG", save_all=True, append_images=[Image.new("RGB", (16, 16))])
    with pytest.raises(Refusal) as refused:
        parse(buffer.getvalue(), "image/png")
    assert refused.value.code == "animated_image_unsupported"
    with pytest.raises(Refusal) as refused:
        parse(png_bytes()[:40], "image/png")
    assert refused.value.code == "malformed_image"


# --------------------------------------------------------------------------- isolation
def test_memory_watchdog_kills_a_worker_that_exceeds_its_bound(tmp_path):
    hog = tmp_path / "hog.py"
    hog.write_text("import sys\nsys.stdin.buffer.read()\nblocks=[]\nfor i in range(64):\n"
                   "    b=bytearray(32*1024*1024)\n    b[::16384]=b'\\x01'*len(b[::16384])\n    blocks.append(b)\n"
                   "print('allocated')\n")
    with pytest.raises(WorkerLimitExceeded) as limited:
        run_worker(Path(hog), b"{}", b"", timeout=30, memory_bytes=256 * 1024 * 1024, output_bytes=1024)
    assert limited.value.code == "worker_memory_limit"


def test_wall_clock_and_output_bounds(tmp_path):
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(30)\n")
    with pytest.raises(WorkerLimitExceeded) as limited:
        run_worker(Path(sleeper), b"{}", b"", timeout=0.5, memory_bytes=512 * 1024 * 1024, output_bytes=1024)
    assert limited.value.code == "worker_timeout"
    chatty = tmp_path / "chatty.py"
    chatty.write_text("import sys\nsys.stdout.write('x' * 100000)\n")
    with pytest.raises(WorkerLimitExceeded) as limited:
        run_worker(Path(chatty), b"{}", b"", timeout=10, memory_bytes=512 * 1024 * 1024, output_bytes=1024)
    assert limited.value.code == "worker_output_limit"


def test_guard_description_is_honest_per_platform():
    guards = describe_guards()
    expected = {"darwin": "phys_footprint_watchdog"}.get(sys.platform, "rlimit_as_and_rss_watchdog")
    assert guards["memory"] == expected and guards["wall_clock"] == "parent_enforced"


def test_worker_never_puts_the_application_package_on_its_path():
    worker = Path(__file__).resolve().parents[1] / "apps/api/bean_api/general_research/_pdf_worker.py"
    source = worker.read_text()
    assert "sys.path.insert" not in source and "spec_from_file_location" in source
