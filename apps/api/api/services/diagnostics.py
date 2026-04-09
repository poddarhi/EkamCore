"""Diagnostics export: build a ZIP of system information for admin troubleshooting.

EXCLUDES all PII: query text, file paths, names, emails, face data, document content.
"""

from __future__ import annotations

import io
import json
import platform
import re
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.models.audit_log import AuditLog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# PII Stripper
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# Names: sequences of 2+ capitalized words (simple heuristic)
_NAME_RE = re.compile(r"\b[A-Z][a-z]{1,20}\s+[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})?\b")


def strip_pii(text: str) -> str:
    """Remove email addresses, phone numbers, and probable names from text."""
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _NAME_RE.sub("[NAME]", text)
    return text


def strip_pii_from_dict(data: dict) -> dict:
    """Recursively strip PII from all string values in a dict."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = strip_pii(value)
        elif isinstance(value, dict):
            result[key] = strip_pii_from_dict(value)
        elif isinstance(value, list):
            result[key] = [
                strip_pii_from_dict(v) if isinstance(v, dict)
                else strip_pii(v) if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------


def _build_system_info() -> dict:
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "environment": settings.ENVIRONMENT,
        "current_phase": "Phase 1 — Sprint 6",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Service health
# ---------------------------------------------------------------------------


async def _build_service_health() -> dict:
    """Fetch current health status (same logic as /health endpoint)."""
    from api.routers.health import health_check
    try:
        return await health_check()
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Container stats
# ---------------------------------------------------------------------------


def _build_container_stats() -> dict:
    """Try to get docker stats. Returns empty dict if docker is unavailable."""
    try:
        result = subprocess.run(
            [
                "docker", "stats", "--no-stream",
                "--format", '{"container":"{{.Name}}","cpu":"{{.CPUPerc}}","mem_usage":"{{.MemUsage}}","mem_pct":"{{.MemPerc}}","net_io":"{{.NetIO}}","block_io":"{{.BlockIO}}"}',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"available": False, "error": "docker stats failed"}

        containers = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return {"available": True, "containers": containers}
    except FileNotFoundError:
        return {"available": False, "error": "docker not found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "error": "docker stats timed out"}
    except Exception as e:
        return {"available": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Audit log summary (counts only, no PII)
# ---------------------------------------------------------------------------


async def _build_audit_summary(db: AsyncSession) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=7)  # naive UTC to match column type

    stmt = (
        select(AuditLog.action, func.count())
        .where(AuditLog.created_at >= cutoff)
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "period": "last_7_days",
        "cutoff": cutoff.isoformat(),
        "events_by_action": {action: count for action, count in rows},
        "total_events": sum(count for _, count in rows),
    }


# ---------------------------------------------------------------------------
# Recent errors (sanitized)
# ---------------------------------------------------------------------------


def _build_recent_errors() -> list[dict]:
    """Return placeholder — real implementation would read from log aggregator.

    In production, this would query a log file, journald, or log aggregator.
    For now, return an empty list since structlog outputs to stdout and we
    don't have a persistent log store yet.
    """
    return []


# ---------------------------------------------------------------------------
# ZIP builder
# ---------------------------------------------------------------------------


async def build_diagnostics_zip(db: AsyncSession) -> bytes:
    """Build a ZIP file containing all diagnostics sections."""
    buf = io.BytesIO()

    system_info = _build_system_info()
    service_health = await _build_service_health()
    container_stats = _build_container_stats()
    audit_summary = await _build_audit_summary(db)
    recent_errors = _build_recent_errors()

    # Sanitize everything through PII stripper
    system_info = strip_pii_from_dict(system_info)
    service_health = strip_pii_from_dict(service_health) if isinstance(service_health, dict) else service_health
    container_stats = strip_pii_from_dict(container_stats)
    audit_summary = strip_pii_from_dict(audit_summary)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system_info.json", json.dumps(system_info, indent=2))
        zf.writestr("service_health.json", json.dumps(service_health, indent=2))
        zf.writestr("container_stats.json", json.dumps(container_stats, indent=2))
        zf.writestr("audit_log_summary.json", json.dumps(audit_summary, indent=2))
        zf.writestr("recent_errors.json", json.dumps(recent_errors, indent=2))

    logger.info("diagnostics_zip_built", size_bytes=buf.tell())
    return buf.getvalue()
