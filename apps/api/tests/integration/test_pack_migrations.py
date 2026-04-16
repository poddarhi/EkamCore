"""Integration tests for migration 020 (S14-001) — pack_runs + pack_cards."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.db.models.pack_card import PackCard
from api.db.models.pack_run import PackRun


@pytest.mark.asyncio(loop_scope="session")
class TestPackTablesExist:
    @pytest.mark.parametrize("table_name", ["pack_runs", "pack_cards"])
    async def test_table_exists(self, test_session_factory, table_name):
        async with test_session_factory() as db:
            result = await db.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:t"
                ),
                {"t": table_name},
            )
            assert result.scalar() == 1, f"Table {table_name} missing"

    async def test_pack_runs_columns(self, test_session_factory):
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='pack_runs'"
                    )
                )
            ).scalars().all()
        names = set(rows)
        for expected in (
            "id",
            "workspace_id",
            "pack_id",
            "trigger",
            "started_at",
            "finished_at",
            "state",
            "cards_produced",
            "llm_calls_used",
            "error_message",
            "duration_ms",
            "created_at",
            "updated_at",
        ):
            assert expected in names, f"pack_runs missing column {expected}"

    async def test_pack_cards_columns(self, test_session_factory):
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='pack_cards'"
                    )
                )
            ).scalars().all()
        names = set(rows)
        for expected in (
            "id",
            "workspace_id",
            "pack_run_id",
            "card_type",
            "payload_json",
            "target_date",
            "acknowledged_at",
            "acknowledged_action",
            "snoozed_until",
            "created_at",
            "updated_at",
        ):
            assert expected in names, f"pack_cards missing column {expected}"

    async def test_indices_present(self, test_session_factory):
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname='public' "
                        "AND tablename IN ('pack_runs','pack_cards')"
                    )
                )
            ).scalars().all()
        names = set(rows)
        for expected in (
            "ix_pack_runs_workspace",
            "ix_pack_runs_pack",
            "ix_pack_cards_workspace_date",
            "ix_pack_cards_type",
        ):
            assert expected in names, f"missing index {expected}"


@pytest.mark.asyncio(loop_scope="session")
class TestPackConstraints:
    async def test_pack_runs_state_check_rejects_unknown(
        self, test_session_factory, seed_user
    ):
        ws = seed_user["workspace_id"]
        async with test_session_factory() as db:
            bad = PackRun(
                workspace_id=ws,
                pack_id="pla",
                trigger="manual",
                state="bogus",
            )
            db.add(bad)
            with pytest.raises(IntegrityError):
                await db.commit()

    async def test_pack_cards_type_check_rejects_unknown(
        self, test_session_factory, seed_user
    ):
        ws = seed_user["workspace_id"]
        async with test_session_factory() as db:
            run = PackRun(workspace_id=ws, pack_id="pla", trigger="manual")
            db.add(run)
            await db.flush()
            card = PackCard(
                workspace_id=ws,
                pack_run_id=run.id,
                card_type="bogus",
                payload_json={},
                target_date=date(2026, 4, 15),
            )
            db.add(card)
            with pytest.raises(IntegrityError):
                await db.commit()

    async def test_pack_cards_cascade_on_run_delete(
        self, test_session_factory, seed_user
    ):
        ws = seed_user["workspace_id"]
        async with test_session_factory() as db:
            run = PackRun(workspace_id=ws, pack_id="pla", trigger="manual")
            db.add(run)
            await db.flush()
            card = PackCard(
                workspace_id=ws,
                pack_run_id=run.id,
                card_type="follow_up_suggestion",
                payload_json={"person_id": str(uuid4())},
                target_date=date(2026, 4, 15),
            )
            db.add(card)
            await db.commit()
            card_id = card.id
            run_id = run.id

        async with test_session_factory() as db:
            await db.execute(
                text("DELETE FROM pack_runs WHERE id = :rid"), {"rid": run_id}
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                text("SELECT 1 FROM pack_cards WHERE id = :cid"),
                {"cid": card_id},
            )
            assert (
                result.scalar() is None
            ), "pack_cards row should cascade-delete with pack_runs"
