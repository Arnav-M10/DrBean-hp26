"""Application limits for paper admission. These are Dr. Bean choices, not provider limits."""

MAX_PAPER_BYTES = 20 * 1024 * 1024          # one retained paper per source workflow
MAX_PAGES = 50                               # physical pages admitted
MAX_PAGES_PER_BATCH = 8                      # explicitly selected pages per model batch
MAX_TEXT_CHARS_PER_PAGE = 20_000             # extracted native text kept per page
MAX_TEXT_CHARS_TOTAL = 400_000               # across the whole paper
MIN_TEXT_CHARS_FOR_TEXT_LAYER = 40           # below this a page is reported as having no useful text layer
MAX_RENDER_PIXELS = 4_000_000                # one rendered page preview
MAX_RENDER_SCALE = 3.0                       # pixels per PDF point (216 dpi)
DEFAULT_RENDER_SCALE = 1.5                   # 108 dpi
MAX_LABEL_CHARS = 32                         # printed page labels such as "S3" or "iv"

# Worker process bounds (resource isolation, not a complete security sandbox).
WORKER_TIMEOUT_SECONDS = {"inspect": 30, "render": 15, "subset": 15}
WORKER_CPU_SECONDS = {"inspect": 25, "render": 12, "subset": 12}
WORKER_MEMORY_BYTES = 768 * 1024 * 1024
WORKER_OUTPUT_BYTES = 24 * 1024 * 1024

PARSER = "pypdf"
RENDERER = "pypdfium2"
MANIFEST_VERSION = "paper-manifest.v1"
COORDINATES = {
    "pdf": "PDF user space in points (1/72 inch), origin at the bottom-left of the page MediaBox, before /Rotate",
    "render": "pixels, origin top-left of the rendered preview, after /Rotate; pixel = point * scale",
}


def capabilities() -> dict:
    """What the paper path admits, for the server's capability report."""
    return {"media_types": ["application/pdf"], "max_bytes": MAX_PAPER_BYTES, "max_pages": MAX_PAGES,
            "max_pages_per_batch": MAX_PAGES_PER_BATCH, "max_render_pixels": MAX_RENDER_PIXELS,
            "parser": PARSER, "renderer": RENDERER, "manifest_version": MANIFEST_VERSION,
            "executes_document_scripts": False, "follows_links_or_attachments": False,
            "remote_fetching": False, "ocr": False}
