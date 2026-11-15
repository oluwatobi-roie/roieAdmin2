"""Validate and persist private payment screenshots, outside the JSON ledger."""
import base64
import hashlib
import io
import os
import tempfile
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from services.finance import FinanceError, clean_text

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def prepare_proof(raw):
    if not isinstance(raw, dict):
        raise FinanceError("Attach a payment screenshot (PNG, JPEG or WebP).")
    value = raw.get("data_url", "")
    if not isinstance(value, str) or len(value) > 6 * 1024 * 1024:
        raise FinanceError("Payment screenshot must be at most 4 MB.")
    try:
        header, encoded = value.split(",", 1)
        if header not in ("data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"):
            raise ValueError()
        content = base64.b64decode(encoded, validate=True)
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP") or image.width * image.height > 20000000:
                    raise ValueError()
                image.load()
                output = io.BytesIO()
                image.convert("RGB").save(output, format="PNG", optimize=True)
                normalized = output.getvalue()
        if len(normalized) > MAX_IMAGE_BYTES:
            raise ValueError()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise FinanceError("Choose a valid PNG, JPEG or WebP screenshot under 4 MB and 20 megapixels.") from exc
    digest = hashlib.sha256(normalized).hexdigest()
    name = clean_text(raw.get("name", "Payment screenshot"), "Screenshot name", 200)
    return {"sha256": digest, "name": name, "content_type": "image/png", "size": len(normalized)}, normalized


def save_proof(directory, proof, content):
    folder = Path(directory) / "payment-proofs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (proof["sha256"] + ".png")
    if path.exists():
        return
    fd, temporary = tempfile.mkstemp(dir=folder, prefix="proof-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
