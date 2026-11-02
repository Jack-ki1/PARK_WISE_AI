"""Media storage: local filesystem (default) or Vercel Blob (serverless).

A *reference* is what the database columns hold. In local mode it is an absolute
path under ``PARKWISE_DATA_DIR`` (unchanged from previous versions, so existing
rows keep resolving); in blob mode it is the object key, e.g.
``uploads/<video-id>/original.mp4``. Every reader in this module accepts either,
so pipeline and API code never branches on the backend except through these calls.

Layout for new objects (both backends): ``<category>/<video-id>/<filename>``.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)

LOCAL = "local"
BLOB = "blob"
CATEGORIES = ("uploads", "previews", "processed", "segments", "models")
# Explicit types win over mimetypes: .mp4/.mov resolve inconsistently across hosts.
CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/x-m4v",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".onnx": "application/octet-stream",
}

_scratch_root: Path | None = None
_scratch_lock = threading.Lock()


class StorageError(RuntimeError):
    """The configured backend could not serve this object."""


def backend() -> str:
    return BLOB if settings.storage_backend.strip().lower() == BLOB else LOCAL


def is_blob() -> bool:
    return backend() == BLOB


def _client():
    from . import blob_http

    return blob_http.client()


def content_type_for(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return CONTENT_TYPES.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def _safe(filename: str) -> str:
    """Object names come from callers, never from user-supplied paths."""
    cleaned = os.path.basename(str(filename)).replace("..", "").strip()
    return cleaned or f"file-{uuid.uuid4().hex[:8]}"


def _root() -> Path:
    return Path(settings.data_dir).expanduser().resolve()


def key_for(category: str, video_id: str, filename: str) -> str:
    if category not in CATEGORIES:
        raise ValueError(f"unknown storage category '{category}'")
    return f"{category}/{_safe(video_id)}/{_safe(filename)}"


def ref_for(category: str, video_id: str, filename: str) -> str:
    """Reference a caller stores in the database for a future object."""
    key = key_for(category, video_id, filename)
    return str(key) if is_blob() else str(_root() / key)


def _from_ref(ref: str) -> str:
    """Object key behind a reference (absolute local paths map onto their key)."""
    if not ref:
        raise StorageError("empty storage reference")
    path = Path(ref)
    if path.is_absolute():
        try:
            return path.relative_to(_root()).as_posix()
        except ValueError:
            # A reference from another data dir (e.g. a restored DB) still reads
            # straight off the local filesystem.
            return ref
    return ref


def local_file(category: str, video_id: str, filename: str) -> Path:
    """A path the caller can write to for this object.

    Local mode returns the destination itself; blob mode returns scratch space
    that the pipeline can hand to OpenCV/ffmpeg before the upload.
    """
    if is_blob():
        directory = scratch_dir(category)
        return directory / f"{_safe(video_id)}-{uuid.uuid4().hex[:8]}-{_safe(filename)}"
    target = Path(ref_for(category, video_id, filename))
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def scratch_dir(category: str = "tmp") -> Path:
    """Writable directory for intermediate files (/tmp on serverless)."""
    global _scratch_root
    with _scratch_lock:
        if _scratch_root is not None and _scratch_root.is_dir():
            return _ensure(_scratch_root / category)
        candidates = []
        if settings.tmp_dir:
            candidates.append(Path(settings.tmp_dir).expanduser())
        candidates.append(Path(tempfile.gettempdir()) / "parkwise")
        for candidate in candidates:
            try:
                probe = candidate / ".write-test"
                probe.parent.mkdir(parents=True, exist_ok=True)
                probe.write_bytes(b"")
                probe.unlink(missing_ok=True)
            except OSError:
                continue
            _scratch_root = candidate
            return _ensure(candidate / category)
        raise StorageError("no writable temporary directory available for video processing")


def _ensure(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve(ref: str) -> Path:
    """Local filesystem path for a reference (blob references must be downloaded)."""
    path = Path(ref)
    if path.is_absolute():
        return path
    root = _root()
    resolved = (root / path).resolve()
    if root not in resolved.parents:
        raise StorageError(f"storage reference escapes the data directory: {ref}")
    return resolved


def exists(ref: str) -> bool:
    if not ref:
        return False
    if is_blob() and not Path(ref).is_absolute():
        return _client().head(ref) is not None
    try:
        return resolve(ref).is_file()
    except StorageError:
        return False


def size_bytes(ref: str) -> int | None:
    if not ref:
        return None
    if is_blob() and not Path(ref).is_absolute():
        meta = _client().head(ref)
        return int(meta.get("size", 0) or 0) if meta else None
    path = resolve(ref)
    return path.stat().st_size if path.is_file() else None


def url_for(ref: str) -> str | None:
    """Direct object URL in blob mode; None when this API serves the bytes itself."""
    if not ref or not (is_blob() and not Path(ref).is_absolute()):
        return None
    return _client().url(ref)


def read_bytes(ref: str) -> bytes:
    if is_blob() and not Path(ref).is_absolute():
        return _client().get_bytes(ref)
    return resolve(ref).read_bytes()


def download_to_tmp(ref: str, *, suffix: str = "") -> Path:
    """Readable local path for a reference: the file itself, or a cached copy.

    OpenCV and ffmpeg need a real path, so blob-mode processing stages the object
    into scratch space first. The copy is keyed by reference and reused.
    """
    if not is_blob() or Path(ref).is_absolute():
        return resolve(ref)
    directory = scratch_dir("in")
    target = directory / f"{uuid.uuid5(uuid.NAMESPACE_URL, ref).hex[:16]}{suffix or Path(ref).suffix}"
    if target.is_file() and target.stat().st_size > 0:
        return target
    _client().download_to_file(ref, target)
    return target


def save_file(ref: str, source: Path, *, content_type: str | None = None, move: bool = True) -> str:
    """Publish a file that already exists on the local disk; returns the reference."""
    source = Path(source)
    size = source.stat().st_size
    ctype = content_type or content_type_for(ref)
    if is_blob() and not Path(ref).is_absolute():
        _client().put_file(ref, source, content_type=ctype)
        if move:
            source.unlink(missing_ok=True)
        _record_asset(ref, size, ctype)
        return ref
    target = resolve(ref)
    if target != source.resolve():
        _ensure(target.parent)
        if move:
            shutil.move(str(source), str(target))
        else:
            shutil.copyfile(source, target)
    _forget_asset(str(target))
    return str(target)


def save_bytes(ref: str, data: bytes, *, content_type: str | None = None) -> str:
    ctype = content_type or content_type_for(ref)
    if is_blob() and not Path(ref).is_absolute():
        _client().put_bytes(ref, data, content_type=ctype)
        _record_asset(ref, len(data), ctype)
        return ref
    target = resolve(ref)
    _ensure(target.parent)
    staging = target.with_name(f"{target.name}.{os.getpid()}.part")
    staging.write_bytes(data)
    os.replace(staging, target)
    return str(target)


def delete(ref: str) -> None:
    if not ref:
        return
    key = _from_ref(ref)
    if is_blob() and not Path(ref).is_absolute():
        try:
            _client().delete(ref)
        except Exception as exc:  # pragma: no cover - a leaked object is not fatal
            logger.warning("could not delete blob %s: %s", ref, exc)
    else:
        try:
            resolve(ref).unlink(missing_ok=True)
        except (OSError, StorageError) as exc:
            logger.warning("could not delete %s: %s", ref, exc)
    _forget_asset(key)
    _forget_asset(ref)


def purge_video(video_id: str, refs: list[str]) -> None:
    """Delete known references and everything stored under this video's prefixes."""
    for ref in refs:
        delete(ref)
    safe_id = _safe(video_id)
    if is_blob():
        keys: list[str] = []
        for category in CATEGORIES:
            prefix = f"{category}/{safe_id}/"
            try:
                keys.extend(_client().list_keys(prefix))
            except Exception as exc:  # pragma: no cover - best effort cleanup
                logger.warning("could not list blob prefix %s: %s", prefix, exc)
        for key in keys:
            delete(key)
        return
    for category in CATEGORIES:
        directory = _root() / category / safe_id
        if directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)


def browser_upload_target(category: str, video_id: str, filename: str) -> dict:
    """Describe the object a browser is about to upload directly to storage.

    Video bytes must not transit a serverless function (the request-body cap is a
    few megabytes), so the browser PUTs straight to the blob store. The client
    token for that PUT is minted by the web tier with ``createClientToken`` from
    ``@vercel/blob``; this API stays the authority on *whether* the upload may
    happen (RBAC + quota) and on registering whatever actually arrived.
    """
    if not is_blob():
        raise StorageError("browser-direct uploads require PARKWISE_STORAGE=blob")
    key = key_for(category, video_id, filename)
    store = _client()
    return {
        "key": key,
        "access": store.access,
        "content_type": content_type_for(key),
        "max_bytes": settings.max_upload_mb * 1024 * 1024,
    }


def adopt_browser_upload(ref: str) -> int:
    """Account for an object the browser already uploaded; returns its size."""
    size = size_bytes(ref)
    if size is None:
        raise StorageError(f"no uploaded object found at {ref}")
    _record_asset(ref, size, content_type_for(ref))
    return size


# ----------------------------------------------------------------- usage accounting
# Blob mode cannot walk a directory, so writes record the object here and the quota
# report sums these rows (see billing.storage_bytes).

def _record_asset(ref: str, size: int, content_type: str) -> None:
    from ..database import SessionLocal
    from ..models import MediaAsset

    key = _from_ref(ref)
    parts = key.split("/")
    video_id = parts[1] if len(parts) >= 3 else None
    db = SessionLocal()
    try:
        row = db.query(MediaAsset).filter(MediaAsset.key == key).first()
        if row is None:
            db.add(
                MediaAsset(
                    id=str(uuid.uuid4()),
                    key=key[:512],
                    video_id=video_id,
                    bytes=size,
                    content_type=content_type[:120],
                )
            )
        else:
            row.bytes = size
            row.content_type = content_type[:120]
        db.commit()
    except Exception as exc:  # pragma: no cover - accounting must not fail a write
        db.rollback()
        logger.warning("could not record storage asset %s: %s", key, exc)
    finally:
        db.close()


def _forget_asset(ref: str) -> None:
    if not ref:
        return
    from ..database import SessionLocal
    from ..models import MediaAsset

    key = _from_ref(ref)[:512]
    db = SessionLocal()
    try:
        db.query(MediaAsset).filter(MediaAsset.key == key).delete(synchronize_session=False)
        db.commit()
    except Exception:  # pragma: no cover
        db.rollback()
    finally:
        db.close()


def assets_bytes(db) -> int:
    from sqlalchemy import func

    from ..models import MediaAsset

    return int(db.query(func.coalesce(func.sum(MediaAsset.bytes), 0)).scalar() or 0)
