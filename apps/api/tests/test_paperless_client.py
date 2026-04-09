"""Unit tests for the PaperlessNGX API client (S07-001).

All HTTP calls are intercepted by injecting a mock httpx.AsyncClient
directly onto the PaperlessClient instance — no network required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from api.errors import AuthenticationError, NotFoundError, ServiceUnavailableError
from api.services.paperless.client import PaperlessClient, get_paperless_client
from api.services.paperless.models import (
    PaperlessCorrespondent,
    PaperlessDocType,
    PaperlessDocument,
    PaperlessSearchResult,
    PaperlessTag,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
    content: bytes = b"",
) -> Mock:
    """Build a mock httpx.Response."""
    r = Mock(spec=httpx.Response)
    r.status_code = status_code
    r.json = Mock(return_value=json_data if json_data is not None else {})
    r.content = content
    if status_code >= 400:
        r.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=Mock(),
                response=Mock(status_code=status_code),
            )
        )
    else:
        r.raise_for_status = Mock(return_value=r)
    return r


def _doc_payload(**overrides: object) -> dict:
    """Minimal valid document payload from the Paperless API."""
    base: dict = {
        "id": 1,
        "title": "Test Invoice",
        "content": "Invoice text content",
        "correspondent": 10,
        "document_type": 5,
        "tags": [1, 2, 3],
        "created": "2024-01-15T10:00:00Z",
        "modified": "2024-03-01T12:00:00Z",
        "added": "2024-01-16T08:00:00Z",
        "archive_serial_number": None,
        "original_file_name": "invoice.pdf",
    }
    base.update(overrides)
    return base


def _paginated(results: list, *, next_url: str | None = None) -> dict:
    return {"count": len(results), "next": next_url, "previous": None, "results": results}


@pytest.fixture
def client_and_mock() -> tuple[PaperlessClient, AsyncMock]:
    """Return a PaperlessClient whose httpx.AsyncClient is replaced by a mock."""
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False
    pc = PaperlessClient(base_url="http://paperless-test:8000/api", token="test-token")
    pc._http = mock_http
    return pc, mock_http


# ── health_check ──────────────────────────────────────────────────────────────


async def test_health_check_returns_true_on_200(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(200))
    assert await pc.health_check() is True
    mock_http.get.assert_awaited_once()


async def test_health_check_returns_false_on_timeout(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    assert await pc.health_check() is False


async def test_health_check_returns_false_on_connect_error(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    assert await pc.health_check() is False


async def test_health_check_returns_false_on_401(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(401))
    assert await pc.health_check() is False


# ── search_documents ──────────────────────────────────────────────────────────


async def test_search_documents_with_query(client_and_mock):
    pc, mock_http = client_and_mock
    payload = _paginated([_doc_payload()])
    mock_http.get = AsyncMock(return_value=_mock_response(200, payload))

    result = await pc.search_documents("invoice")

    assert isinstance(result, PaperlessSearchResult)
    assert result.count == 1
    assert len(result.results) == 1
    doc = result.results[0]
    assert doc.id == 1
    assert doc.title == "Test Invoice"
    assert doc.correspondent_id == 10
    assert doc.document_type_id == 5
    assert doc.tag_ids == [1, 2, 3]

    # Verify "query" param was forwarded
    call_kwargs = mock_http.get.call_args
    assert call_kwargs.kwargs["params"]["query"] == "invoice"


async def test_search_documents_empty_query_omits_query_param(client_and_mock):
    pc, mock_http = client_and_mock
    payload = _paginated([])
    mock_http.get = AsyncMock(return_value=_mock_response(200, payload))

    await pc.search_documents("")

    call_kwargs = mock_http.get.call_args
    assert "query" not in (call_kwargs.kwargs.get("params") or {})


async def test_search_documents_pagination_params(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(200, _paginated([])))

    await pc.search_documents("test", page=3, page_size=10)

    params = mock_http.get.call_args.kwargs["params"]
    assert params["page"] == 3
    assert params["page_size"] == 10


# ── get_document ──────────────────────────────────────────────────────────────


async def test_get_document_returns_model(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(200, _doc_payload(id=42)))

    doc = await pc.get_document(42)

    assert isinstance(doc, PaperlessDocument)
    assert doc.id == 42
    assert doc.original_file_name == "invoice.pdf"
    assert mock_http.get.call_args.args[0].endswith("/documents/42/")


async def test_get_document_404_raises_not_found(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(404))

    with pytest.raises(NotFoundError) as exc_info:
        await pc.get_document(999)
    assert exc_info.value.error_code == "DOCUMENT_NOT_FOUND"


# ── get_document_content ──────────────────────────────────────────────────────


async def test_get_document_content_returns_string(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(
        return_value=_mock_response(200, _doc_payload(content="Full OCR text here"))
    )

    text = await pc.get_document_content(1)

    assert text == "Full OCR text here"


async def test_get_document_content_empty_when_no_content(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(
        return_value=_mock_response(200, _doc_payload(content=""))
    )

    assert await pc.get_document_content(1) == ""


# ── get_document_thumb / get_document_download ────────────────────────────────


async def test_get_document_thumb_returns_bytes(client_and_mock):
    pc, mock_http = client_and_mock
    img_bytes = b"\x89PNG\r\n..."
    mock_http.get = AsyncMock(return_value=_mock_response(200, content=img_bytes))

    result = await pc.get_document_thumb(1)

    assert result == img_bytes
    assert mock_http.get.call_args.args[0].endswith("/documents/1/thumb/")


async def test_get_document_download_returns_bytes(client_and_mock):
    pc, mock_http = client_and_mock
    pdf_bytes = b"%PDF-1.4 ..."
    mock_http.get = AsyncMock(return_value=_mock_response(200, content=pdf_bytes))

    result = await pc.get_document_download(1)

    assert result == pdf_bytes
    assert mock_http.get.call_args.args[0].endswith("/documents/1/download/")


# ── list_correspondents ───────────────────────────────────────────────────────


async def test_list_correspondents_single_page(client_and_mock):
    pc, mock_http = client_and_mock
    payload = _paginated(
        [
            {"id": 1, "name": "ACME Corp", "slug": "acme-corp", "match": "", "matching_algorithm": 1},
            {"id": 2, "name": "Bank Ltd", "slug": "bank-ltd", "match": "", "matching_algorithm": 0},
        ]
    )
    mock_http.get = AsyncMock(return_value=_mock_response(200, payload))

    result = await pc.list_correspondents()

    assert len(result) == 2
    assert all(isinstance(c, PaperlessCorrespondent) for c in result)
    assert result[0].name == "ACME Corp"
    assert result[1].slug == "bank-ltd"


async def test_list_correspondents_auto_paginates(client_and_mock):
    pc, mock_http = client_and_mock
    page1 = _paginated(
        [{"id": 1, "name": "A", "slug": "a"}],
        next_url="http://paperless-test:8000/api/correspondents/?page=2",
    )
    page2 = _paginated([{"id": 2, "name": "B", "slug": "b"}])
    mock_http.get = AsyncMock(
        side_effect=[_mock_response(200, page1), _mock_response(200, page2)]
    )

    result = await pc.list_correspondents()

    assert len(result) == 2
    assert mock_http.get.await_count == 2


# ── list_tags ─────────────────────────────────────────────────────────────────


async def test_list_tags(client_and_mock):
    pc, mock_http = client_and_mock
    payload = _paginated(
        [{"id": 7, "name": "inbox", "slug": "inbox", "colour": 1, "is_inbox_tag": True}]
    )
    mock_http.get = AsyncMock(return_value=_mock_response(200, payload))

    result = await pc.list_tags()

    assert len(result) == 1
    assert isinstance(result[0], PaperlessTag)
    assert result[0].is_inbox_tag is True


# ── list_document_types ───────────────────────────────────────────────────────


async def test_list_document_types(client_and_mock):
    pc, mock_http = client_and_mock
    payload = _paginated([{"id": 3, "name": "Invoice", "slug": "invoice"}])
    mock_http.get = AsyncMock(return_value=_mock_response(200, payload))

    result = await pc.list_document_types()

    assert len(result) == 1
    assert isinstance(result[0], PaperlessDocType)
    assert result[0].name == "Invoice"


# ── list_documents_modified_since ─────────────────────────────────────────────


async def test_list_documents_modified_since_yields_newer_docs(client_and_mock):
    pc, mock_http = client_and_mock
    since = datetime(2024, 3, 1, tzinfo=timezone.utc)

    # Two docs: one newer, one at the boundary (should be excluded)
    payload = _paginated(
        [
            _doc_payload(id=10, modified="2024-04-01T10:00:00Z"),
            _doc_payload(id=11, modified="2024-03-01T00:00:00Z"),  # == since → excluded
        ]
    )
    mock_http.get = AsyncMock(return_value=_mock_response(200, payload))

    results = [doc async for doc in pc.list_documents_modified_since(since)]

    assert len(results) == 1
    assert results[0].id == 10


async def test_list_documents_modified_since_stops_at_boundary(client_and_mock):
    """Should NOT fetch page 2 once a doc at/before the boundary is found."""
    pc, mock_http = client_and_mock
    since = datetime(2024, 3, 1, tzinfo=timezone.utc)

    page1 = _paginated(
        [_doc_payload(id=1, modified="2024-02-01T00:00:00Z")],  # before since
        next_url="http://test/page2",
    )
    mock_http.get = AsyncMock(return_value=_mock_response(200, page1))

    results = [doc async for doc in pc.list_documents_modified_since(since)]

    assert results == []
    assert mock_http.get.await_count == 1  # never fetched page 2


async def test_list_documents_modified_since_multi_page(client_and_mock):
    pc, mock_http = client_and_mock
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)

    page1 = _paginated(
        [_doc_payload(id=1, modified="2024-04-01T00:00:00Z")],
        next_url="http://test/page2",
    )
    page2 = _paginated([_doc_payload(id=2, modified="2024-03-01T00:00:00Z")])
    mock_http.get = AsyncMock(
        side_effect=[_mock_response(200, page1), _mock_response(200, page2)]
    )

    results = [doc async for doc in pc.list_documents_modified_since(since)]

    assert len(results) == 2
    assert {r.id for r in results} == {1, 2}


# ── Error handling ────────────────────────────────────────────────────────────


async def test_timeout_raises_service_unavailable(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await pc.search_documents("test")
    assert exc_info.value.error_code == "PAPERLESS_UNAVAILABLE"


async def test_connect_error_raises_service_unavailable(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await pc.get_document(1)
    assert exc_info.value.error_code == "PAPERLESS_UNAVAILABLE"


async def test_401_raises_authentication_error(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(401))

    with pytest.raises(AuthenticationError) as exc_info:
        await pc.search_documents("test")
    assert exc_info.value.error_code == "PAPERLESS_AUTH_FAILED"


async def test_403_raises_authentication_error(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(403))

    with pytest.raises(AuthenticationError) as exc_info:
        await pc.list_tags()
    assert exc_info.value.error_code == "PAPERLESS_AUTH_FAILED"


async def test_500_raises_service_unavailable(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.get = AsyncMock(return_value=_mock_response(500))

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await pc.list_correspondents()
    assert exc_info.value.error_code == "PAPERLESS_UNAVAILABLE"


# ── close ─────────────────────────────────────────────────────────────────────


async def test_close_shuts_down_http_client(client_and_mock):
    pc, mock_http = client_and_mock
    mock_http.is_closed = False
    mock_http.aclose = AsyncMock()

    await pc.close()

    mock_http.aclose.assert_awaited_once()
    assert pc._http is None


async def test_close_is_idempotent_when_already_none():
    pc = PaperlessClient(base_url="http://test", token="tok")
    # _http is None — should not raise
    await pc.close()


# ── Singleton ─────────────────────────────────────────────────────────────────


def test_get_paperless_client_returns_same_instance():
    import api.services.paperless.client as mod
    mod._singleton = None  # reset for test isolation

    c1 = get_paperless_client()
    c2 = get_paperless_client()

    assert c1 is c2
    assert isinstance(c1, PaperlessClient)

    mod._singleton = None  # clean up


def test_get_paperless_client_uses_settings():
    import api.services.paperless.client as mod
    mod._singleton = None

    with (
        patch("api.services.paperless.client.settings") as mock_settings,
    ):
        mock_settings.PAPERLESS_URL = "http://custom:9000/api"
        mock_settings.PAPERLESS_API_TOKEN = "secret-tok"
        c = get_paperless_client()

    assert c._base_url == "http://custom:9000/api"
    assert c._token == "secret-tok"
    mod._singleton = None
