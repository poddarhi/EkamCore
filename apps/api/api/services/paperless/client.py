"""PaperlessNGX REST API client (S07-001).

A typed async client for the PaperlessNGX v3 REST API.  One singleton is
created at import time from ``settings``; callers use ``get_paperless_client()``
to obtain it.

Error mapping
─────────────
  Timeout / network failure → ServiceUnavailableError("PAPERLESS_UNAVAILABLE")
  401 / 403                 → AuthenticationError("PAPERLESS_AUTH_FAILED")
  404 on a specific doc     → NotFoundError("DOCUMENT_NOT_FOUND")
  Any other 4xx/5xx         → ServiceUnavailableError("PAPERLESS_UNAVAILABLE")
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import TypeVar

import httpx
import structlog

from api.config import settings
from api.errors import AuthenticationError, NotFoundError, ServiceUnavailableError
from api.services.paperless.models import (
    PaperlessCorrespondent,
    PaperlessDocType,
    PaperlessDocument,
    PaperlessSearchResult,
    PaperlessTag,
)

logger = structlog.get_logger()

_DEFAULT_TIMEOUT = httpx.Timeout(10.0, read=30.0)
_PAGE_SIZE = 25

_T = TypeVar("_T")


class PaperlessClient:
    """Async HTTP client for the PaperlessNGX REST API.

    Wraps a lazily-created ``httpx.AsyncClient`` so connection pools are
    reused across calls.  The client is thread-safe for concurrent async
    callers within a single event loop.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        """Return (or lazily create) the shared AsyncClient."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                headers={"Authorization": f"Token {self._token}"},
                timeout=self._timeout,
            )
        return self._http

    async def close(self) -> None:
        """Close the underlying connection pool. Call during app shutdown."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _get(self, path: str, **params: object) -> httpx.Response:
        """Authenticated GET with structured error mapping.

        Keyword arguments beyond ``path`` are forwarded as query parameters.
        ``None`` values are excluded so callers can use optional params freely.
        """
        url = self._url(path)
        clean_params = {k: v for k, v in params.items() if v is not None} or None

        try:
            r = await self._client().get(url, params=clean_params)
        except httpx.TimeoutException:
            logger.warning("paperless_timeout", url=url)
            raise ServiceUnavailableError(
                error_code="PAPERLESS_UNAVAILABLE",
                message="Paperless request timed out.",
            )
        except httpx.RequestError:
            logger.warning("paperless_unreachable", url=url)
            raise ServiceUnavailableError(
                error_code="PAPERLESS_UNAVAILABLE",
                message="Paperless is unreachable.",
            )

        if r.status_code in (401, 403):
            logger.warning("paperless_auth_failed", url=url, status=r.status_code)
            raise AuthenticationError(
                error_code="PAPERLESS_AUTH_FAILED",
                message="Paperless API token is invalid or missing.",
            )
        if r.status_code == 404:
            raise NotFoundError(
                error_code="DOCUMENT_NOT_FOUND",
                message="Paperless document not found.",
            )
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            logger.warning("paperless_http_error", url=url, status=r.status_code)
            raise ServiceUnavailableError(
                error_code="PAPERLESS_UNAVAILABLE",
                message=f"Paperless returned HTTP {r.status_code}.",
            )
        return r

    async def _list_all(self, path: str, model_cls: type[_T]) -> list[_T]:
        """Auto-paginate a Paperless list endpoint and return every item."""
        items: list[_T] = []
        page = 1
        while True:
            r = await self._get(path, page=page, page_size=100)
            data = r.json()
            items.extend(
                model_cls.model_validate(item)  # type: ignore[attr-defined]
                for item in data.get("results", [])
            )
            if data.get("next") is None:
                break
            page += 1
        return items

    # ── Public API ────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if Paperless is reachable and the API token is valid."""
        try:
            await self._get("/")
            return True
        except (ServiceUnavailableError, AuthenticationError):
            return False

    async def search_documents(
        self,
        query: str,
        page: int = 1,
        page_size: int = _PAGE_SIZE,
    ) -> PaperlessSearchResult:
        """Full-text search.  An empty *query* lists all documents."""
        r = await self._get(
            "/documents/",
            page=page,
            page_size=page_size,
            query=query or None,
        )
        return PaperlessSearchResult.model_validate(r.json())

    async def get_document(self, doc_id: int) -> PaperlessDocument:
        """Fetch a single document's metadata and OCR content."""
        r = await self._get(f"/documents/{doc_id}/")
        return PaperlessDocument.model_validate(r.json())

    async def get_document_content(self, doc_id: int) -> str:
        """Return the full OCR/extracted text for a document."""
        doc = await self.get_document(doc_id)
        return doc.content

    async def get_document_thumb(self, doc_id: int) -> bytes:
        """Return the WebP thumbnail bytes for a document."""
        r = await self._get(f"/documents/{doc_id}/thumb/")
        return r.content

    async def get_document_download(self, doc_id: int) -> bytes:
        """Return the archived PDF bytes for a document."""
        r = await self._get(f"/documents/{doc_id}/download/")
        return r.content

    async def list_correspondents(self) -> list[PaperlessCorrespondent]:
        """Return all correspondents (auto-paginated)."""
        return await self._list_all("/correspondents/", PaperlessCorrespondent)

    async def list_tags(self) -> list[PaperlessTag]:
        """Return all tags (auto-paginated)."""
        return await self._list_all("/tags/", PaperlessTag)

    async def list_document_types(self) -> list[PaperlessDocType]:
        """Return all document types (auto-paginated)."""
        return await self._list_all("/document_types/", PaperlessDocType)

    async def list_documents_modified_since(
        self,
        since: datetime,
    ) -> AsyncIterator[PaperlessDocument]:
        """Yield documents ordered newest-modified-first, stopping at *since*.

        *since* must be a timezone-aware datetime.  Suitable for incremental
        sync: pass the cursor from the previous run.
        """
        page = 1
        while True:
            r = await self._get(
                "/documents/",
                page=page,
                page_size=_PAGE_SIZE,
                ordering="-modified",
            )
            data = r.json()
            exhausted = False
            for item in data.get("results", []):
                doc = PaperlessDocument.model_validate(item)
                if doc.modified is not None and doc.modified <= since:
                    exhausted = True
                    break
                yield doc
            if exhausted or data.get("next") is None:
                break
            page += 1


# ── Module-level singleton ────────────────────────────────────────────────────

_singleton: PaperlessClient | None = None


def get_paperless_client() -> PaperlessClient:
    """Return (or lazily create) the module-level PaperlessClient singleton."""
    global _singleton
    if _singleton is None:
        _singleton = PaperlessClient(
            base_url=settings.PAPERLESS_URL,
            token=settings.PAPERLESS_API_TOKEN,
        )
    return _singleton
