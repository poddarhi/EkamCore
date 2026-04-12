"""Tests for metrics service, middleware, and API (G-15 / ART-27)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.metric import Metric
from api.services import metrics_service
from api.services.metrics_service import (
    _parse_latencies,
    _percentile,
    classify_endpoint,
)


# ── Unit tests: endpoint classification ────────────────────────────────────


class TestClassifyEndpoint:
    def test_query_endpoint(self):
        assert classify_endpoint("/api/v1/query") == "query"

    def test_search_endpoint(self):
        assert classify_endpoint("/api/v1/search") == "search"

    def test_today_endpoint(self):
        assert classify_endpoint("/api/v1/today") == "today"

    def test_auth_login(self):
        assert classify_endpoint("/api/v1/auth/login") == "auth"

    def test_auth_refresh(self):
        assert classify_endpoint("/api/v1/auth/refresh") == "auth"

    def test_admin_endpoint(self):
        assert classify_endpoint("/api/v1/admin/audit-log") == "admin"

    def test_metrics_endpoint(self):
        assert classify_endpoint("/api/v1/metrics/current") == "admin"

    def test_health_endpoint(self):
        assert classify_endpoint("/health") == "health"

    def test_unknown_endpoint(self):
        assert classify_endpoint("/random/path") == "other"


# ── Unit tests: percentile math ────────────────────────────────────────────


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single_value(self):
        assert _percentile([100.0], 50) == 100.0

    def test_p50(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(values, 50) == 3.0

    def test_p95(self):
        values = list(range(1, 101))  # 1..100
        assert _percentile(values, 95) == pytest.approx(95.05, abs=0.1)

    def test_p99(self):
        values = list(range(1, 101))
        assert _percentile(values, 99) == pytest.approx(99.01, abs=0.1)

    def test_monotonic(self):
        values = list(range(100))
        p50 = _percentile(values, 50)
        p95 = _percentile(values, 95)
        p99 = _percentile(values, 99)
        assert p50 < p95 < p99


class TestParseLatencies:
    def test_empty(self):
        assert _parse_latencies([]) == []

    def test_valid_members(self):
        members = ["1234.5:100.0", "1234.6:200.5", "1234.7:50.25"]
        assert _parse_latencies(members) == [100.0, 200.5, 50.25]

    def test_invalid_members_skipped(self):
        members = ["valid:100", "noColon", "not:number", "1:5.5"]
        assert _parse_latencies(members) == [100.0, 5.5]


# ── Redis recording tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRecordRequest:
    async def test_record_request_increments_counters(self):
        mock_redis = AsyncMock()
        pipe = Mock()
        pipe.incr = Mock(return_value=pipe)
        pipe.expire = Mock(return_value=pipe)
        pipe.zadd = Mock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[1, True, 1, True, 1, True])
        mock_redis.pipeline = Mock(return_value=pipe)

        with patch(
            "api.services.metrics_service.get_redis", return_value=mock_redis
        ):
            await metrics_service.record_request(
                path="/api/v1/today",
                method="GET",
                status=200,
                latency_ms=125.5,
            )

        pipe.execute.assert_awaited_once()
        # Verify counters were queued
        assert pipe.incr.call_count >= 2  # count + status

    async def test_record_request_handles_redis_failure(self):
        mock_redis = AsyncMock()
        mock_redis.pipeline = Mock(side_effect=Exception("redis down"))

        with patch(
            "api.services.metrics_service.get_redis", return_value=mock_redis
        ):
            # Should not raise
            await metrics_service.record_request(
                path="/api/v1/today",
                method="GET",
                status=200,
                latency_ms=50,
            )

    async def test_record_query_type(self):
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        with patch(
            "api.services.metrics_service.get_redis", return_value=mock_redis
        ):
            await metrics_service.record_query_type("deterministic")

        mock_redis.incr.assert_awaited_once()

    async def test_record_llm_latency(self):
        mock_redis = AsyncMock()
        mock_redis.zadd = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        with patch(
            "api.services.metrics_service.get_redis", return_value=mock_redis
        ):
            await metrics_service.record_llm_latency("phi3:mini", 4250.3)

        mock_redis.zadd.assert_awaited_once()


# ── Query tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestQueryMetrics:
    async def test_query_empty(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            result = await metrics_service.query_metrics(
                db=db, workspace_id=seed_user["workspace_id"]
            )
        assert result == []

    async def test_query_returns_inserted_metric(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            now = datetime.now(timezone.utc)
            db.add(
                Metric(
                    metric_key="test.metric",
                    metric_value={"value": 42},
                    period_start=now - timedelta(hours=1),
                    period_end=now,
                    workspace_id=seed_user["workspace_id"],
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await metrics_service.query_metrics(
                db=db, workspace_id=seed_user["workspace_id"]
            )
        assert len(result) >= 1
        assert any(m.metric_key == "test.metric" for m in result)

    async def test_query_filter_by_key_prefix(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            now = datetime.now(timezone.utc)
            db.add(
                Metric(
                    metric_key="api_latency.query",
                    metric_value={"p50_ms": 50.0},
                    period_start=now - timedelta(hours=1),
                    period_end=now,
                    workspace_id=seed_user["workspace_id"],
                )
            )
            db.add(
                Metric(
                    metric_key="daily.request_counts",
                    metric_value={"total": 100},
                    period_start=now - timedelta(hours=1),
                    period_end=now,
                    workspace_id=seed_user["workspace_id"],
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await metrics_service.query_metrics(
                db=db,
                workspace_id=seed_user["workspace_id"],
                metric_key="api_latency",
            )
        keys = {m.metric_key for m in result}
        assert "api_latency.query" in keys
        assert "daily.request_counts" not in keys

    async def test_query_workspace_isolation(self, test_session_factory, seed_user):
        """Metrics from another workspace must not leak."""
        other_ws = uuid4()
        async with test_session_factory() as db:
            now = datetime.now(timezone.utc)
            db.add(
                Metric(
                    metric_key="test.isolation",
                    metric_value={"value": 1},
                    period_start=now - timedelta(hours=1),
                    period_end=now,
                    workspace_id=seed_user["workspace_id"],
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await metrics_service.query_metrics(
                db=db, workspace_id=other_ws
            )
        assert all(m.workspace_id != seed_user["workspace_id"] for m in result)


# ── API endpoint tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMetricsEndpoint:
    async def _promote_admin(self, test_session_factory, user_id):
        """Promote a test user to admin role."""
        from sqlalchemy import update
        from api.db.models.user import User

        async with test_session_factory() as db:
            await db.execute(
                update(User).where(User.id == user_id).values(role="admin")
            )
            await db.commit()

    async def test_metrics_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/metrics", params={"workspace_id": str(uuid4())})
        assert resp.status_code == 401

    async def test_metrics_requires_admin(
        self, client: AsyncClient, auth_tokens: dict
    ):
        # seed_user has 'standard' role by default
        resp = await client.get(
            "/api/v1/metrics",
            params={"workspace_id": str(auth_tokens["workspace_id"])},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "ADMIN_REQUIRED"

    async def test_metrics_current_requires_admin(
        self, client: AsyncClient, auth_tokens: dict
    ):
        resp = await client.get(
            "/api/v1/metrics/current",
            params={"workspace_id": str(auth_tokens["workspace_id"])},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403

    async def test_metrics_list_as_admin(
        self, client: AsyncClient, seed_user: dict, test_session_factory
    ):
        # Promote to admin
        await self._promote_admin(test_session_factory, seed_user["user_id"])

        # Login again to get fresh token with admin role
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": seed_user["password"]},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        resp = await client.get(
            "/api/v1/metrics",
            params={"workspace_id": str(seed_user["workspace_id"])},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert "count" in data
        assert isinstance(data["metrics"], list)

    async def test_metrics_current_as_admin(
        self, client: AsyncClient, seed_user: dict, test_session_factory
    ):
        await self._promote_admin(test_session_factory, seed_user["user_id"])

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": seed_user["password"]},
        )
        token = login_resp.json()["access_token"]

        # Mock Redis scan_iter to return empty
        mock_redis = AsyncMock()

        async def empty_scan_iter(match=None):
            return
            yield  # unreachable — makes it an async generator

        mock_redis.scan_iter = empty_scan_iter

        with patch(
            "api.services.metrics_service.get_redis", return_value=mock_redis
        ):
            resp = await client.get(
                "/api/v1/metrics/current",
                params={"workspace_id": str(seed_user["workspace_id"])},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert "workspace_id" in data
        assert "usage_today" in data
        assert "latency_current_hour" in data
        assert "cumulative" in data

    async def test_metrics_cross_workspace_denied(
        self, client: AsyncClient, seed_user: dict, test_session_factory
    ):
        await self._promote_admin(test_session_factory, seed_user["user_id"])

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": seed_user["password"]},
        )
        token = login_resp.json()["access_token"]

        other_ws = uuid4()
        resp = await client.get(
            "/api/v1/metrics",
            params={"workspace_id": str(other_ws)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "WORKSPACE_ACCESS_DENIED"
