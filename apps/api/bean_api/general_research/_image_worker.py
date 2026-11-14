"""Isolated fixed-path PNG/JPEG worker: full bounded decode plus an optional bounded preview.

Run as ``python -I _image_worker.py`` by ``sandbox.run_worker``. The original bytes
are never modified. A preview is produced only when the displayed image exceeds the
page-image bound or carries a non-default EXIF orientation; it is a declared derived
representation with its own digest, never a silent replacement of the source.
"""
import base64
import hashlib
import importlib.util
import io
import json
import os
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


L = _load("limits", os.path.join(HERE, "limits.py"))
R = _load("resource_policy", os.path.join(os.path.dirname(HERE), "resource_policy.py"))
KNOWN = {"malformed_image", "image_pixel_limit", "animated_image_unsupported", "image_mode_unsupported",
         "source_too_large", "invalid_command", "decoder_setup_failed", "resource_limit"}
ORIENTATION_SWAPS = {5, 6, 7, 8}


class Refused(ValueError):
    pass


def main():
    header = sys.stdin.buffer.readline(4096)
    try:
        command = json.loads(header)
    except ValueError:
        raise Refused("invalid_command") from None
    if not isinstance(command, dict) or command.get("operation") != "inspect":
        raise Refused("invalid_command")
    R.apply_limits(cpu_seconds=L.WORKER_CPU_SECONDS["image"], memory_bytes=L.WORKER_MEMORY_BYTES, open_files=64)
    raw = sys.stdin.buffer.read(L.MAX_ASSET_BYTES + 1)
    if not raw or len(raw) > L.MAX_ASSET_BYTES:
        raise Refused("source_too_large")
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = L.MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in ("PNG", "JPEG"):
            raise Refused("malformed_image")
        width, height = image.size
        if (width <= 0 or height <= 0 or width > L.MAX_IMAGE_SIDE_PX or height > L.MAX_IMAGE_SIDE_PX
                or width * height > L.MAX_IMAGE_PIXELS):
            raise Refused("image_pixel_limit")
        if getattr(image, "n_frames", 1) != 1:
            raise Refused("animated_image_unsupported")
        if image.mode not in ("1", "L", "LA", "P", "PA", "RGB", "RGBA", "CMYK", "I;16", "I", "YCbCr"):
            raise Refused("image_mode_unsupported")
        orientation = image.getexif().get(274, 1)
        orientation = orientation if orientation in range(1, 9) else 1
        media_type = "image/png" if image.format == "PNG" else "image/jpeg"
        mode = image.mode
    with Image.open(io.BytesIO(raw)) as image:
        image.verify()
    display_width, display_height = (height, width) if orientation in ORIENTATION_SWAPS else (width, height)
    needs_preview = (orientation != 1 or max(display_width, display_height) > L.RENDER_MAX_SIDE_PX
                     or mode not in ("L", "RGB", "RGBA", "P"))
    preview = None
    with Image.open(io.BytesIO(raw)) as image:
        if needs_preview and media_type == "image/jpeg":
            longer = max(width, height)
            target = max(1, (L.RENDER_MAX_SIDE_PX * width) // longer), max(1, (L.RENDER_MAX_SIDE_PX * height) // longer)
            image.draft("RGB", target)  # decode at a reduced JPEG scale when possible
        image.load()  # full decode: truncated or corrupt data fails here
        if needs_preview:
            shown = ImageOps.exif_transpose(image)
            if shown.mode not in ("L", "RGB", "RGBA"):
                shown = shown.convert("RGBA" if "A" in shown.mode else "RGB")
            shown.thumbnail((L.RENDER_MAX_SIDE_PX, L.RENDER_MAX_SIDE_PX))
            buffer = io.BytesIO()
            if media_type == "image/jpeg":
                shown.convert("RGB").save(buffer, format="JPEG", quality=90, optimize=False)
            else:
                shown.save(buffer, format="PNG", compress_level=6)
            content = buffer.getvalue()
            preview = {"media_type": media_type, "width": shown.width, "height": shown.height,
                       "sha256": hashlib.sha256(content).hexdigest(),
                       "base64": base64.b64encode(content).decode("ascii"),
                       "reason": "exif_orientation_applied" if orientation != 1 else
                                 "downscaled_to_page_image_bound" if max(display_width, display_height)
                                 > L.RENDER_MAX_SIDE_PX else "color_mode_converted"}
    sys.stdout.write(json.dumps({"media_type": media_type, "width": width, "height": height,
                                 "display_width": display_width, "display_height": display_height,
                                 "orientation": orientation, "mode": mode, "preview": preview},
                                separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fixed codes only; never decoder internals or source content
        if isinstance(exc, Refused):
            code = str(exc)
        elif isinstance(exc, R.ResourceSetupError) or isinstance(exc, ImportError):
            code = "decoder_setup_failed"
        elif isinstance(exc, MemoryError):
            code = "resource_limit"
        elif exc.__class__.__name__ == "DecompressionBombError" or exc.__class__.__name__ == "DecompressionBombWarning":
            code = "image_pixel_limit"
        else:
            code = "malformed_image"
        print(code if code in KNOWN else "malformed_image", file=sys.stderr)
        raise SystemExit(1) from None
