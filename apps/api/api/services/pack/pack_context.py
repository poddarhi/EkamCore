"""PackContext — sandboxed data access for pack execution (S14-003).

A ``PackContext`` is the *only* object a pack callable is handed
at runtime. Every read, write, query, and LLM call flows through
a method on this class, and every method begins with a
``_require_capability`` check. The capability set, resource
limits, allowed card types, and consent state are all fixed at
construction time by :class:`PackContextFactory` — the pack
cannot mutate them, and it cannot reach around the context to
the underlying session because the session is held as a private
attribute and never exposed.

Hard rules (ART-13 §6 / ART-14):

1. **Workspace isolation.** ``workspace_id`` is passed into the
   constructor by the factory. The pack never supplies it; every
   query filters on ``self._workspace_id`` exactly once. A
   capability check that would leak cross-workspace data is a
   bug — the defence is to never expose the session or the raw
   workspace id, plus a test in
   ``tests/security/test_pack_context_isolation.py`` that asserts
   a PackContext for workspace A cannot see a row in workspace B.
2. **Capability-first.** Every public method calls
   ``self._require_capability(cap)`` *before* touching any data.
   The factory already stripped consent-gated capabilities when
   consent is off, so a pack that runs with reduced data simply
   sees ``CAPABILITY_DENIED`` on the face methods and can degrade
   gracefully instead of crashing.
3. **No raw SQL.** The underlying ``AsyncSession`` is held as a
   private attribute, not a property. The only data a pack sees
   is whatever a ``get_*`` / ``traverse_*`` method returns.
4. **LLM quota.** Every ``ask_llm`` call increments
   ``_llm_calls_used``; exceeding ``resource_limits.max_llm_calls_per_run``
   raises :class:`PackLlmQuotaExceededError` immediately. No
   override.
5. **Output sanitization.** LLM responses and card payloads are
   passed through :func:`sanitizer.sanitize_text` /
   :func:`sanitize_payload` before they can leave the context.
   Plain text in, plain text out — even if a prompt tricks the
   model into emitting HTML.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.pack_card import PackCard
from api.db.models.photo_asset import PhotoAsset
from api.db.models.reminder import Reminder
from api.db.models.trusted_person import TrustedPerson
from api.errors import (
    CapabilityDeniedError,
    PackLlmQuotaExceededError,
)
from api.services import audit
from api.services.pack.manifest_loader import ResourceLimits
from api.services.pack.sanitizer import sanitize_payload, sanitize_text

logger = structlog.get_logger()


#: Signature of the async LLM callable the factory injects.
#: Accepts ``(prompt, max_tokens, temperature)`` and returns the
#: raw response string. Broken out so tests can pass a stub
#: without touching the real Ollama client.
LlmCallable = Callable[[str, int, float], Awaitable[str]]


class PackContext:
    """Scoped, capability-gated data access handed to a pack callable.

    See module docstring for the hard rules. Callers should build
    instances via :class:`PackContextFactory`, never directly.
    """

    def __init__(
        self,
        *,
        workspace_id: UUID,
        capabilities: set[str],
        resource_limits: ResourceLimits,
        allowed_card_types: set[str],
        consent_active: bool,
        pack_id: str,
        pack_run_id: UUID | None,
        db: AsyncSession,
        llm_callable: LlmCallable | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._capabilities = frozenset(capabilities)
        self._resource_limits = resource_limits
        self._allowed_card_types = frozenset(allowed_card_types)
        self._consent_active = consent_active
        self._pack_id = pack_id
        self._pack_run_id = pack_run_id
        # Held private so packs can't reach the session.
        self._db = db
        self._llm_callable = llm_callable
        self._llm_calls_used = 0
        self._cards_produced: list[dict[str, Any]] = []

    # ── Public inspection ─────────────────────────────────────────────

    @property
    def workspace_id(self) -> UUID:
        return self._workspace_id

    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    @property
    def consent_active(self) -> bool:
        return self._consent_active

    @property
    def llm_calls_used(self) -> int:
        return self._llm_calls_used

    @property
    def cards(self) -> list[dict[str, Any]]:
        """List of queued cards. Consumed by :class:`PackExecutor`
        after the pack returns successfully."""
        return list(self._cards_produced)

    # ── Capability-gated reads ────────────────────────────────────────

    async def get_contacts(
        self, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Contact]:
        self._require_capability("read:contacts")
        stmt = (
            select(Contact)
            .where(
                and_(
                    Contact.workspace_id == self._workspace_id,
                    Contact.deleted_at.is_(None),
                )
            )
            .order_by(Contact.display_name)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_events_in_range(
        self, *, start: datetime, end: datetime, limit: int = 200
    ) -> Sequence[CalendarEvent]:
        self._require_capability("read:calendar_events")
        stmt = (
            select(CalendarEvent)
            .where(
                and_(
                    CalendarEvent.workspace_id == self._workspace_id,
                    CalendarEvent.start_at >= start,
                    CalendarEvent.start_at <= end,
                )
            )
            .order_by(CalendarEvent.start_at)
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_reminders(
        self, *, limit: int = 100, overdue_only: bool = False
    ) -> Sequence[Reminder]:
        self._require_capability("read:reminders")
        conditions = [
            Reminder.workspace_id == self._workspace_id,
            Reminder.deleted_at.is_(None),
        ]
        if overdue_only:
            conditions.extend(
                [
                    Reminder.is_completed.is_(False),
                    Reminder.due_at.is_not(None),
                    Reminder.due_at < datetime.utcnow(),
                ]
            )
        stmt = (
            select(Reminder)
            .where(and_(*conditions))
            .order_by(Reminder.due_at.asc().nulls_last())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_overdue_reminders(
        self, *, limit: int = 100
    ) -> Sequence[Reminder]:
        return await self.get_reminders(limit=limit, overdue_only=True)

    async def get_persons(
        self, *, limit: int = 100
    ) -> Sequence[TrustedPerson]:
        self._require_capability("read:trusted_persons")
        self._require_face_consent()
        stmt = (
            select(TrustedPerson)
            .where(
                and_(
                    TrustedPerson.workspace_id == self._workspace_id,
                    TrustedPerson.deleted_at.is_(None),
                )
            )
            .order_by(TrustedPerson.display_name)
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_person_by_id(
        self, person_id: UUID
    ) -> TrustedPerson | None:
        self._require_capability("read:trusted_persons")
        self._require_face_consent()
        stmt = select(TrustedPerson).where(
            and_(
                TrustedPerson.id == person_id,
                TrustedPerson.workspace_id == self._workspace_id,
                TrustedPerson.deleted_at.is_(None),
            )
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get_edges_for_person(
        self, person_id: UUID, *, limit: int = 200
    ) -> Sequence[GraphEdge]:
        self._require_capability("read:graph_edges")
        self._require_face_consent()
        stmt = (
            select(GraphEdge)
            .where(
                and_(
                    GraphEdge.workspace_id == self._workspace_id,
                    GraphEdge.from_type == "trusted_person",
                    GraphEdge.from_id == person_id,
                )
            )
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_files(
        self, *, limit: int = 100
    ) -> Sequence[File]:
        self._require_capability("read:files")
        stmt = (
            select(File)
            .where(
                and_(
                    File.workspace_id == self._workspace_id,
                    File.deleted_at.is_(None),
                )
            )
            .order_by(File.created_at.desc())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_photos(
        self, *, limit: int = 100
    ) -> Sequence[PhotoAsset]:
        self._require_capability("read:photos")
        stmt = (
            select(PhotoAsset)
            .where(
                and_(
                    PhotoAsset.workspace_id == self._workspace_id,
                    PhotoAsset.deleted_at.is_(None),
                )
            )
            .order_by(PhotoAsset.taken_at.desc().nulls_last())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_photos_for_person(
        self, person_id: UUID, *, limit: int = 50
    ) -> Sequence[PhotoAsset]:
        self._require_capability("read:photos")
        self._require_capability("read:graph_edges")
        self._require_face_consent()
        stmt = (
            select(PhotoAsset)
            .join(
                GraphEdge,
                and_(
                    GraphEdge.to_id == PhotoAsset.id,
                    GraphEdge.to_type == "photo_asset",
                    GraphEdge.edge_type == "appears_in",
                    GraphEdge.from_type == "trusted_person",
                    GraphEdge.from_id == person_id,
                    GraphEdge.workspace_id == self._workspace_id,
                ),
            )
            .where(
                and_(
                    PhotoAsset.workspace_id == self._workspace_id,
                    PhotoAsset.deleted_at.is_(None),
                )
            )
            .order_by(PhotoAsset.taken_at.desc().nulls_last())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    # ── Capability-gated writes ───────────────────────────────────────

    async def create_reminder(
        self,
        *,
        title: str,
        due_at: datetime | None = None,
        priority: str = "none",
        notes: str | None = None,
        created_by: UUID,
        person_id: UUID | None = None,  # noqa: ARG002 — recorded in audit only
    ) -> Reminder:
        """Insert a reminder via the write-through pipeline.

        ``created_by`` is the workspace owner or pack-designated
        system user — never the pack itself, which has no identity
        in the user table. Audit log entry records the operation as
        pack-initiated so downstream ops can distinguish synthetic
        reminders from user-created ones.
        """
        self._require_capability("write:reminders")
        clean_title = sanitize_text(title, max_len=500)
        clean_notes = sanitize_text(notes, max_len=2000) if notes else None
        reminder = Reminder(
            workspace_id=self._workspace_id,
            title=clean_title,
            due_at=due_at,
            priority=priority,
            notes=clean_notes,
            is_completed=False,
            write_through_status="pending",
            created_by=created_by,
        )
        self._db.add(reminder)
        await self._db.flush()
        await audit.log_event(
            db=self._db,
            action="pack_reminder_created",
            object_type="reminder",
            object_id=reminder.id,
            user_id=created_by,
            workspace_id=self._workspace_id,
            metadata={
                "pack_id": self._pack_id,
                "pack_run_id": (
                    str(self._pack_run_id) if self._pack_run_id else None
                ),
            },
        )
        return reminder

    # ── Graph traversal ───────────────────────────────────────────────

    async def traverse_graph(
        self, person_id: UUID, *, depth: int = 2, max_edges: int = 500
    ) -> list[GraphEdge]:
        """Breadth-first traversal of ``graph_edges`` starting at
        ``person_id``, bounded by ``depth`` hops and ``max_edges``.

        Scoped to ``self._workspace_id`` on every query. Depth is
        clamped to ``[1, 5]`` so a malicious or buggy pack can't
        cause an O(N^5) scan.
        """
        self._require_capability("query:graph")
        self._require_face_consent()
        depth = max(1, min(int(depth), 5))

        visited_nodes: set[tuple[str, UUID]] = {("trusted_person", person_id)}
        frontier: list[tuple[str, UUID]] = [("trusted_person", person_id)]
        collected: list[GraphEdge] = []

        for _ in range(depth):
            if not frontier or len(collected) >= max_edges:
                break
            next_frontier: list[tuple[str, UUID]] = []
            for node_type, node_id in frontier:
                stmt = (
                    select(GraphEdge)
                    .where(
                        and_(
                            GraphEdge.workspace_id == self._workspace_id,
                            GraphEdge.from_type == node_type,
                            GraphEdge.from_id == node_id,
                        )
                    )
                    .limit(max_edges)
                )
                edges = (await self._db.execute(stmt)).scalars().all()
                for edge in edges:
                    if len(collected) >= max_edges:
                        break
                    collected.append(edge)
                    target = (edge.to_type, edge.to_id)
                    if target not in visited_nodes:
                        visited_nodes.add(target)
                        next_frontier.append(target)
            frontier = next_frontier
        return collected

    # ── LLM invocation ────────────────────────────────────────────────

    async def ask_llm(
        self,
        prompt: str,
        *,
        max_tokens: int = 200,  # noqa: ARG002 — Ollama uses options, not max_tokens
        temperature: float = 0.3,
    ) -> str:
        """Invoke the local LLM under the pack's quota.

        Increments ``llm_calls_used`` **before** the call so a
        failure still counts toward the quota (rate-limit the
        retries, not just the successes). The returned text is
        sanitized to plain text before it leaves the context.
        """
        self._require_capability("invoke:llm")
        if (
            self._llm_calls_used
            >= self._resource_limits.max_llm_calls_per_run
        ):
            raise PackLlmQuotaExceededError(
                error_code="PACK_LLM_QUOTA_EXCEEDED",
                message=(
                    f"pack '{self._pack_id}' exceeded its "
                    f"max_llm_calls_per_run "
                    f"({self._resource_limits.max_llm_calls_per_run})"
                ),
            )
        self._llm_calls_used += 1
        clean_prompt = sanitize_text(prompt, max_len=4000)
        if self._llm_callable is None:
            # No LLM configured — behave as if it returned empty.
            # Tests inject a stub; production always sets one.
            logger.warning(
                "pack_ask_llm_no_callable",
                pack_id=self._pack_id,
            )
            return ""
        raw = await self._llm_callable(
            clean_prompt, 200, float(temperature)
        )
        return sanitize_text(raw, max_len=4000)

    # ── Card production ──────────────────────────────────────────────

    async def produce_card(
        self, card_type: str, payload: dict[str, Any]
    ) -> None:
        """Queue a card for post-run insertion.

        Cards are only persisted after the pack returns
        successfully; the ``PackExecutor`` (S14-004) walks
        ``self.cards`` and writes them in a single transaction.
        The card_type must have been declared in the manifest or
        this raises ``CAPABILITY_DENIED``.
        """
        if card_type not in self._allowed_card_types:
            raise CapabilityDeniedError(
                error_code="CAPABILITY_DENIED",
                message=(
                    f"pack '{self._pack_id}' produced undeclared "
                    f"card_type '{card_type}'"
                ),
            )
        if not isinstance(payload, dict):
            raise CapabilityDeniedError(
                error_code="CAPABILITY_DENIED",
                message="card payload must be a dict",
            )
        clean_payload = sanitize_payload(payload)
        self._cards_produced.append(
            {"card_type": card_type, "payload": clean_payload}
        )

    # ── Pack-card deduplication (S14-006) ───────────────────────────

    async def has_pending_card_for_person(
        self,
        person_id: UUID,
        card_type: str,
        target_date: Any,
    ) -> bool:
        """Return True if a non-acknowledged card of ``card_type`` with
        ``person_id`` in its payload already exists for ``target_date``.

        No capability check — this reads the pack's own output table,
        not user data.
        """
        from api.db.models.pack_card import PackCard as _PC

        stmt = (
            select(_PC.id)
            .where(
                and_(
                    _PC.workspace_id == self._workspace_id,
                    _PC.card_type == card_type,
                    _PC.target_date == target_date,
                    _PC.acknowledged_at.is_(None),
                )
            )
            .limit(50)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        pid_str = str(person_id)
        for row_id in rows:
            card = (
                await self._db.execute(
                    select(_PC.payload_json).where(_PC.id == row_id)
                )
            ).scalar_one_or_none()
            if card and card.get("person_id") == pid_str:
                return True
        return False

    async def is_person_snoozed(
        self,
        person_id: UUID,
        card_type: str,
    ) -> bool:
        """Return True if a snoozed card for ``person_id`` exists
        whose ``snoozed_until`` is in the future."""
        from datetime import date as _date

        from api.db.models.pack_card import PackCard as _PC

        today = _date.today()
        stmt = (
            select(_PC.id)
            .where(
                and_(
                    _PC.workspace_id == self._workspace_id,
                    _PC.card_type == card_type,
                    _PC.snoozed_until.is_not(None),
                    _PC.snoozed_until > today,
                )
            )
            .limit(50)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        pid_str = str(person_id)
        for row_id in rows:
            card = (
                await self._db.execute(
                    select(_PC.payload_json).where(_PC.id == row_id)
                )
            ).scalar_one_or_none()
            if card and card.get("person_id") == pid_str:
                return True
        return False

    # ── Internals ─────────────────────────────────────────────────────

    def _require_capability(self, cap: str) -> None:
        if cap not in self._capabilities:
            raise CapabilityDeniedError(
                error_code="CAPABILITY_DENIED",
                message=f"pack '{self._pack_id}' lacks capability '{cap}'",
                details={"capability": cap, "pack_id": self._pack_id},
            )

    def _require_face_consent(self) -> None:
        if not self._consent_active:
            raise CapabilityDeniedError(
                error_code="CAPABILITY_DENIED",
                message=(
                    f"pack '{self._pack_id}' cannot access face data — "
                    "consent is not active for this workspace"
                ),
                details={"pack_id": self._pack_id},
            )
