"""PackContextFactory (S14-003).

Builds a :class:`PackContext` from a workspace id + a validated
:class:`PackManifest`. Responsibilities:

1. **Capability projection.** Start with the manifest's declared
   capability set, then strip every entry whose registry
   definition has ``requires_consent=True`` if face consent is
   not currently active for the workspace. This is the graceful
   degradation path — a pack keeps running with reduced data
   instead of exploding when consent is off.
2. **Consent precomputation.** Call ``consent_service.is_consent_active``
   exactly once at construction and cache the result. Packs call
   ``PackContext._require_face_consent`` many times; each call
   reads from the cached flag rather than hitting Redis per call.
3. **LLM callable wiring.** Inject a thin wrapper that calls the
   real :mod:`api.services.query.llm_client` under ``P2_PACK``
   priority. Tests pass a stub to bypass Ollama entirely.
"""

from __future__ import annotations

from typing import Awaitable, Callable
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.face import consent_service
from api.services.pack.capability_registry import (
    consent_gated_capabilities,
)
from api.services.pack.manifest_loader import PackManifest
from api.services.pack.pack_context import LlmCallable, PackContext
from api.services.query import llm_client as _llm_client
from api.services.resource_controller import Priority, acquire_slot

logger = structlog.get_logger()


async def _default_llm_callable(
    prompt: str, max_tokens: int, temperature: float
) -> str:
    """Production LLM invocation path — P2 slot + small model.

    Tests inject a stub via ``PackContextFactory.create`` so this
    function is bypassed entirely in unit tests. It's imported
    lazily so a test that never calls ``ask_llm`` doesn't need to
    mock out Ollama at all.
    """
    del max_tokens  # Ollama uses ``options``, not max_tokens
    async with acquire_slot(Priority.P2_PACK):
        return await _llm_client.call_llm(
            messages=[{"role": "user", "content": prompt}],
            model=_llm_client.SMALL_MODEL,
            timeout_s=30.0,
            temperature=temperature,
        )


class PackContextFactory:
    """Builds a :class:`PackContext` for a single pack execution.

    Stateless — safe to reuse across runs. Callers should pass a
    custom ``llm_callable`` only in tests.
    """

    def __init__(
        self,
        *,
        llm_callable: LlmCallable | None = None,
        consent_checker: Callable[
            [UUID, AsyncSession], Awaitable[bool]
        ]
        | None = None,
    ) -> None:
        self._llm_callable = llm_callable or _default_llm_callable
        self._consent_checker = (
            consent_checker or consent_service.is_consent_active
        )

    async def create(
        self,
        *,
        workspace_id: UUID,
        manifest: PackManifest,
        db: AsyncSession,
        pack_run_id: UUID | None = None,
    ) -> PackContext:
        consent_active = await self._consent_checker(workspace_id, db)
        effective_caps: set[str] = set(manifest.capabilities)
        if not consent_active:
            stripped = effective_caps & consent_gated_capabilities()
            if stripped:
                logger.info(
                    "pack_context_consent_caps_stripped",
                    pack_id=manifest.pack_id,
                    workspace_id=str(workspace_id),
                    stripped=sorted(stripped),
                )
            effective_caps -= consent_gated_capabilities()
        return PackContext(
            workspace_id=workspace_id,
            capabilities=effective_caps,
            resource_limits=manifest.resource_limits,
            allowed_card_types=set(manifest.card_types),
            consent_active=consent_active,
            pack_id=manifest.pack_id,
            pack_run_id=pack_run_id,
            db=db,
            llm_callable=self._llm_callable,
        )
