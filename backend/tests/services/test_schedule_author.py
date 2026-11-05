"""ФИО в тексте не даёт права менять расписание другого человека."""

from datetime import date

import pytest
from sqlalchemy import select

from teamtime.bot.feedback import group_feedback
from teamtime.db.models import Resolution, TelegramIdentity
from teamtime.parsing import ParseStatus
from teamtime.services import manual
from teamtime.services.facts import current_plans
from teamtime.services.ingest import ingest
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db


async def test_another_linked_person_cannot_overwrite_existing_plan(session):
    await f.forum(session)
    owner = await f.employee(session, tg_id=501)
    await f.employee(session, "Петров П.П.", tg_id=502)
    own = await ingest(session, f.message(f.schedule_text(), thread=f.SCHEDULE_THREAD))
    attempt = await ingest(
        session, f.message(f.schedule_text(Пн="12:00-18:00"), author=502, thread=f.SCHEDULE_THREAD)
    )
    assert attempt.status is ParseStatus.FAILED and attempt.employee_id is None
    assert "posted_for_other" in {i.code for i in attempt.issues}
    plans = await current_plans(session, date(2026, 10, 26), date(2026, 11, 1))
    assert len(plans) == 1 and plans[0].employee_id == owner.id
    assert plans[0].parse_result_id == own.parse_result_id
    feedback = group_feedback(attempt, AppSettings(), bot_username=None)
    assert feedback.reaction == "🤔" and "не записано" in feedback.reply
    with pytest.raises(manual.EditError, match="привязку"):
        await manual.resolve_parse(
            session, attempt.parse_result_id, Resolution.ACCEPTED, actor="admin"
        )


async def test_correcting_header_allows_own_plan(session):
    await f.forum(session)
    await f.employee(session, tg_id=501)
    sender = await f.employee(session, "Петров П.П.", tg_id=502)
    await ingest(
        session, f.message(f.schedule_text(), author=502, thread=f.SCHEDULE_THREAD, message_id=42)
    )
    fixed = await ingest(
        session,
        f.message(
            f.schedule_text("Петров П.П."),
            author=502,
            thread=f.SCHEDULE_THREAD,
            message_id=42,
            edited=True,
        ),
    )
    assert fixed.status is ParseStatus.OK and fixed.employee_id == sender.id


async def test_unknown_name_is_not_silently_replaced_with_sender(session):
    await f.forum(session)
    await f.employee(session, tg_id=501)
    attempt = await ingest(
        session, f.message(f.schedule_text("Сидоров С.С."), thread=f.SCHEDULE_THREAD)
    )
    assert attempt.status is ParseStatus.FAILED
    assert "schedule_person_mismatch" in {i.code for i in attempt.issues}
    assert await current_plans(session, date(2026, 10, 26), date(2026, 11, 1)) == []


async def test_linking_unknown_sender_to_other_person_does_not_approve_forged_header(session):
    await f.forum(session)
    await f.employee(session)
    sender = await f.employee(session, "Петров П.П.")
    await ingest(session, f.message(f.schedule_text(), author=777, thread=f.SCHEDULE_THREAD))
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == 777)
    )
    await manual.link_identity(session, identity.id, sender.id, AppSettings(), actor="admin")
    assert await current_plans(session, date(2026, 10, 26), date(2026, 11, 1)) == []
