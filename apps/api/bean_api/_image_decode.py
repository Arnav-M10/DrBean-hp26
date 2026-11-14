"""Private fixed-path image decoder process, intentionally without application imports."""
import io
import json
import sys
import warnings

try:
    from .resource_policy import ResourceSetupError, apply_limits
except ImportError:  # The parent invokes this fixed file directly, with a minimal environment.
    from resource_policy import ResourceSetupError, apply_limits


def main():
    apply_limits(cpu_seconds=3, memory_bytes=512 * 1024 * 1024)
    from PIL import Image
    max_pixels = 12_000_000
    max_source_bytes = 5 * 1024 * 1024
    max_decoded_bytes = 48 * 1024 * 1024
    Image.MAX_IMAGE_PIXELS = max_pixels
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    raw = sys.stdin.buffer.read(max_source_bytes + 1)
    if not raw or len(raw) > max_source_bytes:
        raise ValueError("source_too_large")
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError("unsupported_media_type")
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > max_pixels:
            raise ValueError("pixel_limit")
        if width * height * 4 > max_decoded_bytes:
            raise ValueError("decoded_memory_limit")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("animated_image_unsupported")
        if image.getexif().get(274, 1) != 1:
            raise ValueError("orientation_unsupported")
        if image.mode not in {"L", "LA", "P", "RGB", "RGBA"}:
            raise ValueError("image_mode_unsupported")
        media_type = "image/png" if image.format == "PNG" else "image/jpeg"
    with Image.open(io.BytesIO(raw)) as image:
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
    print(json.dumps({"observed_media_type": media_type, "width": width, "height": height}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Only known fixed codes leave this parser; no decoder input or raw traceback.
        known = {"pixel_limit", "decoded_memory_limit", "animated_image_unsupported", "orientation_unsupported", "image_mode_unsupported"}
        code = "decoder_setup_failed" if isinstance(exc, ResourceSetupError) else str(exc) if isinstance(exc, ValueError) and str(exc) in known else "malformed_image"
        print(code, file=sys.stderr)
        raise SystemExit(1) from None
