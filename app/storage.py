"""Content-addressed blob store.

Blobs live on disk under `data/blobs/ab/cd/<digest>`, sharded two levels by the
digest so no directory ends up holding every image in the school. The database
holds only metadata; the filesystem holds bytes. Neither Postgres nor an object
store is the right home for a few gigabytes of exam photos on a single machine.

Because the name *is* the digest, writing the same image twice is a no-op and
two rows can never disagree about what a file contains.
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage

from .config import Settings

# Pillow refuses images above this many pixels as a decompression-bomb guard.
# A scanned A4 at 600dpi is ~35MP, so the default 89MP ceiling is left alone;
# this only pins it so a future Pillow default change cannot surprise us.
PILImage.MAX_IMAGE_PIXELS = 120_000_000

_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "HEIF": "image/heif",
}


class UnsupportedImage(ValueError):
    pass


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    mime: str
    width: int
    height: int
    bytes: int


class BlobStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._blobs = settings.blobs
        self._derivatives = settings.derivatives
        self._blobs.mkdir(parents=True, exist_ok=True)
        self._derivatives.mkdir(parents=True, exist_ok=True)

    # ── paths ────────────────────────────────────────────────────────────────

    def path_for(self, digest: str) -> Path:
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ValueError("not a sha256 hex digest")
        return self._blobs / digest[:2] / digest[2:4] / digest

    def exists(self, digest: str) -> bool:
        return self.path_for(digest).is_file()

    # ── writing ──────────────────────────────────────────────────────────────

    def put(self, data: bytes) -> StoredBlob:
        """Validate, hash, and store. Re-storing identical bytes is free."""
        if not data:
            raise UnsupportedImage("empty upload")
        if len(data) > self._settings.max_upload_bytes:
            raise UnsupportedImage("upload too large")

        try:
            with PILImage.open(io.BytesIO(data)) as probe:
                probe.verify()  # detects truncation; consumes the object
            with PILImage.open(io.BytesIO(data)) as image:
                fmt = (image.format or "").upper()
                width, height = image.size
        except UnsupportedImage:
            raise
        except Exception as exc:  # Pillow raises a wide variety here
            raise UnsupportedImage("not a readable image") from exc

        if fmt not in _MIME_BY_FORMAT:
            raise UnsupportedImage(f"unsupported image format: {fmt or 'unknown'}")

        digest = hashlib.sha256(data).hexdigest()
        target = self.path_for(digest)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, data)

        return StoredBlob(
            sha256=digest,
            mime=_MIME_BY_FORMAT[fmt],
            width=width,
            height=height,
            bytes=len(data),
        )

    # ── reading ──────────────────────────────────────────────────────────────

    def read(self, digest: str) -> bytes:
        return self.path_for(digest).read_bytes()

    def derivative(self, digest: str, width: int) -> Path:
        """A width-limited JPEG rendering, generated on demand and cached.

        The phone's matcher runs at 832x608; handing it a 4000px original costs
        bandwidth and battery for detail that is downscaled away on arrival.

        Everything under the derivative directory is reconstructible, so it can
        be deleted at any time to reclaim disk.
        """
        if width not in self._settings.allowed_master_widths:
            raise ValueError(f"width {width} not offered")

        cached = self._derivatives / f"{digest}_{width}.jpg"
        if cached.is_file():
            return cached

        with PILImage.open(self.path_for(digest)) as image:
            image = image.convert("RGB")
            if image.width > width:
                height = max(1, round(image.height * width / image.width))
                image = image.resize((width, height), PILImage.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=88, optimize=True)

        cached.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(cached, buffer.getvalue())
        return cached


def _atomic_write(target: Path, data: bytes) -> None:
    """Write via a temp file in the same directory, then rename.

    A half-written blob whose name claims to be its own digest is a lie that
    survives restarts; rename(2) within a filesystem is atomic, so a reader
    sees either nothing or the whole file.
    """
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
