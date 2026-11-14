"""Admission, parsing and analysis limits for general research files.

These are Dr. Bean application limits, not provider quotas. Every limit is
enforced by refusing the work with a named code; nothing is silently truncated.
This module imports nothing from the application so that the isolated workers
can load it by path.
"""

MiB = 1024 * 1024

CONTRACT_VERSION = "general-research.v1"
CITATION_NORMALIZATION_VERSION = "citation-normalization.v1"
BBOX_SPACE = "normalized_top_left"

# Upload and analysis selection (shared API contract).
# Paper profile v2: PDFs (papers) may be larger and longer than other files.
# Every other kind keeps the original 5 MiB bound; images sent to the model,
# lab-sheet intake and Counterdex inputs are unchanged.
FILE_PROFILE = "paper-25mib-20p.v2"
MAX_ASSET_BYTES = 5 * MiB                # text, tables, JSON and raster images
MAX_PDF_BYTES = 25 * MiB                 # one paper
MAX_UPLOAD_BYTES = max(MAX_ASSET_BYTES, MAX_PDF_BYTES)
MIN_ANALYSIS_ASSETS = 1
MAX_ANALYSIS_ASSETS = 5
MAX_ANALYSIS_BYTES = 50 * MiB
MAX_SOURCE_NAME_CHARS = 240
MAX_SOURCE_NAME_HEADER_BYTES = 1024
MAX_QUESTION_CHARS = 4000

# PDF structure and decoding. The pre-scan refuses a file before PDFium sees it.
MAX_PDF_PAGES = 20
MAX_PDF_PAGE_SIDE_POINTS = 5000          # about 1.76 m; A0 is 2384 x 3370 points
MIN_PDF_PAGE_SIDE_POINTS = 1
MAX_PDF_OBJECTS = 100_000
MAX_PDF_DECLARED_SIZE = 1_000_000        # trailer /Size
MAX_PDF_NESTING = 64
MAX_PDF_STREAM_DECODED_BYTES = 32 * MiB
MAX_PDF_TOTAL_DECODED_BYTES = 512 * MiB   # all streams together (time bound; image data is not retained)
MAX_PDF_IMAGE_PIXELS = 40_000_000        # one image XObject (a 600 dpi A4 scan is about 35 million)
MAX_PDF_PAGE_IMAGE_PIXELS = 80_000_000   # declared image pixels referenced by all streams together
MAX_PDF_TEXT_CHARS_PER_PAGE = 200_000
MAX_PDF_TEXT_CHARS_TOTAL = 2_000_000       # scales with MAX_PDF_PAGES
MIN_TEXT_LAYER_ALNUM = 20                # fewer alphanumerics: the page has no useful text layer

# Page images sent to the model and shown in the browser (also the live image bound).
RENDER_MAX_SIDE_PX = 1600
RENDER_MAX_PIXELS = 1600 * 1600
RENDER_MAX_SCALE = 3.0

# Ordinary images (PNG/JPEG uploads).
MAX_IMAGE_PIXELS = 50_000_000
MAX_IMAGE_SIDE_PX = 20_000

# Text, delimited tables and JSON.
MAX_TEXT_CHARS = 5 * MiB
MAX_TABLE_ROWS = 200_000
MAX_TABLE_COLUMNS = 512
MAX_FIELD_CHARS = 100_000
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 500_000
TABLE_PREVIEW_ROWS = 20
TEXT_PREVIEW_CHARS = 2000

# Isolated worker processes (resource isolation, not a complete security sandbox).
WORKER_TIMEOUT_SECONDS = {"pdf": 45, "image": 20}
WORKER_CPU_SECONDS = {"pdf": 40, "image": 15}
WORKER_MEMORY_BYTES = 768 * MiB
WORKER_OUTPUT_BYTES = 64 * MiB
WORKER_POLL_SECONDS = 0.005

# Model request shaping. Output counts are also enforced by the response schema.
ANALYSIS_OUTPUT_TOKENS = 4096
ANALYSIS_FIXED_INPUT_OVERHEAD = 1024


def public_limits() -> dict:
    """Limits the browser needs to explain refusals before uploading."""
    return {
        "file_profile": FILE_PROFILE, "max_asset_bytes": MAX_ASSET_BYTES, "max_pdf_bytes": MAX_PDF_BYTES,
        "min_assets_per_analysis": MIN_ANALYSIS_ASSETS,
        "max_assets_per_analysis": MAX_ANALYSIS_ASSETS, "max_analysis_bytes": MAX_ANALYSIS_BYTES,
        "max_pdf_pages": MAX_PDF_PAGES, "max_question_chars": MAX_QUESTION_CHARS,
        "max_source_name_chars": MAX_SOURCE_NAME_CHARS, "max_table_rows": MAX_TABLE_ROWS,
        "max_table_columns": MAX_TABLE_COLUMNS, "max_image_pixels": MAX_IMAGE_PIXELS,
        "page_image_max_side_px": RENDER_MAX_SIDE_PX,
    }
