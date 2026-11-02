"""Vercel Blob access for the storage layer (PARKWISE_STORAGE=blob).

Wraps the official ``vercel-blob`` sync SDK (``vercel.blob.sync``), which resolves
credentials itself: ``BLOB_STORE_ID`` + the Vercel OIDC token on Vercel functions,
or ``BLOB_READ_WRITE_TOKEN`` anywhere else. The import is lazy so a local-mode
install never needs the package.

Objects are addressed by pathname key (``uploads/<video-id>/name.mp4``). A public
store also serves them from its CDN, so the API can hand browsers a direct URL
instead of proxying megabytes through a function.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import quote

from ..config import settings

logger = logging.getLogger(__name__)

CACHE_CONTROL_SECONDS = 300  # re-analysis overwrites a key; keep CDN staleness short


class BlobError(RuntimeError):
    """Blob storage is unavailable (missing package, credentials or object)."""


def _sdk():
    try:
        from vercel.blob import sync as blob
    except ModuleNotFoundError as exc:  # pragma: no cover - local installs lack it
        raise BlobError(
            "PARKWISE_STORAGE=blob needs the official SDK: pip install 'vercel-blob>=0.5,<1.0'"
        ) from exc
    return blob


def _not_found(exc: Exception) -> bool:
    return type(exc).__name__ in {"BlobNotFoundError", "BlobStoreNotFoundError"}


def credentials_present() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("VERCEL_BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_STORE_ID"))


class BlobStore:
    def __init__(self, access: str | None = None, public_url: str | None = None) -> None:
        self.access = (access or settings.blob_access or "public").strip().lower()
        if self.access not in {"public", "private"}:
            raise BlobError("PARKWISE_BLOB_ACCESS must be 'public' or 'private'")
        self.public_url = (public_url if public_url is not None else settings.blob_public_url).rstrip("/")

    # ------------------------------------------------------------------ writes
    def _put(self, key: str, body, *, content_type: str, content_length: int):
        blob = _sdk()
        try:
            return blob.put_blob(
                key,
                body,
                access=self.access,
                content_type=content_type,
                content_length=content_length,
                allow_overwrite=True,
                cache_control_max_age=CACHE_CONTROL_SECONDS,
            )
        except Exception as exc:
            raise BlobError(f"could not store {key}: {exc}") from exc

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> dict:
        result = self._put(key, data, content_type=content_type, content_length=len(data))
        return {"key": key, "url": getattr(result, "url", None), "size": len(data), "content_type": content_type}

    def put_file(self, key: str, path: Path, *, content_type: str) -> dict:
        path = Path(path)
        size = path.stat().st_size
        with path.open("rb") as handle:
            result = self._put(key, handle, content_type=content_type, content_length=size)
        return {"key": key, "url": getattr(result, "url", None), "size": size, "content_type": content_type}

    # ------------------------------------------------------------------- reads
    def head(self, key: str) -> dict | None:
        blob = _sdk()
        try:
            meta = blob.head_blob(key)
        except Exception as exc:
            if _not_found(exc):
                return None
            raise BlobError(f"could not read metadata for {key}: {exc}") from exc
        return {
            "size": int(getattr(meta, "size", 0) or 0),
            "content_type": getattr(getattr(meta, "metadata", None), "content_type", None),
            "url": getattr(meta, "url", None),
        }

    def get_bytes(self, key: str) -> bytes:
        blob = _sdk()
        try:
            return blob.get_blob(key, access=self.access).body
        except Exception as exc:
            if _not_found(exc):
                raise BlobError(f"no such object: {key}") from exc
            raise BlobError(f"could not download {key}: {exc}") from exc

    def download_to_file(self, key: str, target: Path) -> Path:
        """Stream an object into scratch space (video tools need a real path)."""
        blob = _sdk()
        temporary = Path(target).with_suffix(Path(target).suffix + ".part")
        try:
            with blob.stream_blob(key, access=self.access) as stream, temporary.open("wb") as handle:
                for chunk in stream:
                    handle.write(chunk)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            if _not_found(exc):
                raise BlobError(f"no such object: {key}") from exc
            raise BlobError(f"could not download {key}: {exc}") from exc
        temporary.replace(target)
        return target

    def url(self, key: str) -> str | None:
        """CDN URL for a public store object; None when bytes must be proxied."""
        if self.access != "public" or not self.public_url:
            return None
        return f"{self.public_url}/{quote(key)}"

    def list_keys(self, prefix: str) -> list[str]:
        blob = _sdk()
        try:
            return [item.pathname for item in blob.query_blobs(prefix=prefix, page_size=1000)]
        except Exception as exc:
            raise BlobError(f"could not list {prefix}* : {exc}") from exc

    def delete(self, key: str) -> None:
        blob = _sdk()
        try:
            blob.delete_blob(key)
        except Exception as exc:
            if _not_found(exc):
                return
            raise BlobError(f"could not delete {key}: {exc}") from exc


_client: BlobStore | None = None


def client() -> BlobStore:
    global _client
    if _client is None:
        _client = BlobStore()
    return _client


def reset_client() -> None:
    """Drop the cached client (used by tests and after configuration changes)."""
    global _client
    _client = None
