from pathlib import Path
from PIL import Image, UnidentifiedImageError
from backend.config import settings

MAX_BYTES = 200 * 1024
MAX_PIXELS = 20_000_000

def validate_photo(data: bytes, *, required: bool = True) -> bytes | None:
    if len(data) > MAX_BYTES: raise ValueError("Photo must be 200 KB or smaller")
    if not data:
        if required: raise ValueError("Photo is required")
        return None
    try:
        import io
        image = Image.open(io.BytesIO(data))
        if image.format not in ("JPEG", "JPG"): raise ValueError("Upload a JPG or JPEG photo")
        if image.width * image.height > MAX_PIXELS or image.width < 32 or image.height < 32: raise ValueError("Photo dimensions are not supported")
        image.verify()
    except ValueError: raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError): raise ValueError("Photo is not a valid JPEG image")
    return data

def save_photo(worker_id: str, data: bytes) -> Path:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / f"{worker_id}.jpg"
    target.write_bytes(data)
    return target

