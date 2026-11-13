"""Запросы фонда 18/19 и 2/3 числа: одна попытка на получателя и конкретный цикл."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from html import escape
from typing import Any

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.calc.fund import month_start, next_month
from teamtime.core import clock
from teamtime.core.logging import get_logger
from teamtime.db.fund import FundMember, FundPeriod
from teamtime.db.fund_operations import FundBasket, FundLoan, FundNotification, FundReconciliation
from teamtime.db.models import Employee, TelegramIdentity
from teamtime.services import fund_config, fund_ledger, fund_report
from teamtime.services.settings import load_settings

log = get_logger(__name__)


async def candidates(session: AsyncSession) -> list[dict[str, Any]]:
    config = await fund_config.load(session)
    if not config.module_active or not config.enabled or not config.reminders_enabled:
        return []
    settings = await load_settings(session)
    now = clock.now().astimezone(settings.tz)
    scheduled = datetime.combine(
        now.date(), time(config.notification_hour, config.notification_minute), settings.tz
    )
    if not scheduled <= now < scheduled + timedelta(hours=1):
        return []
    until = month_start(
        now.date() if now.day >= 18 else now.date().replace(day=1) - timedelta(days=1)
    )
    people = list(
        await session.scalars(
            select(FundMember)
            .join(Employee, Employee.id == FundMember.employee_id)
            .where(FundMember.active, Employee.is_active)
        )
    )
    if not people:
        return []
    if now.day not in {18, 19, 2, 3}:
        return await overdue_loans(session, people, now)
    results: list[dict[str, Any]] = []
    month = config.first_month
    while month <= until:
        stored = await session.get(FundPeriod, month)
        if stored is None or stored.closed_at is None:
            report = await fund_report.report(session, people[0].employee_id, month)
            for person in people:
                row = next(
                    (r for r in report["rows"] if r["employee"]["id"] == person.employee_id), None
                )
                if row is None:
                    continue
                incomplete = [s for s in row["sources"] if s["state"] != "complete"]
                if now.day in {19, 3} and not incomplete:
                    continue
                if not row["sources"]:
                    continue
                names = ", ".join(escape(s["name"]) for s in (incomplete or row["sources"]))
                results.append(
                    {
                        "employee_id": person.employee_id,
                        "cycle": f"sources:{now.date()}:{month}",
                        "text": (
                            f"💼 <b>Выплаты за {month:%m.%Y}</b>\n\n"
                            f"Укажите фактически полученные суммы на руки: {names}.\n"
                            "Если всё уже внесено, подтвердите «Всё получено». "
                            "Если будут ещё выплаты — «Жду ещё».\n\n"
                            f"Откройте /fund и выберите месяц {month:%m.%Y}."
                        ),
                    }
                )
        month = next_month(month)
    cycle_start = now.date().replace(day=18 if now.day >= 18 else 2)
    for basket in await session.scalars(select(FundBasket).where(FundBasket.active)):
        fresh = await session.scalar(
            select(FundReconciliation.id)
            .where(
                FundReconciliation.basket_id == basket.id, FundReconciliation.as_of >= cycle_start
            )
            .limit(1)
        )
        if now.day in {19, 3} and fresh:
            continue
        results.append(
            {
                "employee_id": basket.owner_id,
                "cycle": f"basket:{now.date()}:{basket.id}",
                "text": (
                    f"🏦 <b>Сверка: {escape(basket.name)}</b>\n\n"
                    f"Подтвердите фактический остаток на {now:%d.%m.%Y} "
                    "через /fund → «Сверить свою корзину». "
                    "Предыдущая сверка не заменяет новый ответ."
                ),
            }
        )
    for person in people:
        if not person.leader:
            continue
        data = await fund_ledger.treasury(session, person.employee_id)
        results.append(
            {
                "employee_id": person.employee_id,
                "cycle": f"summary:{now.date()}",
                "text": (
                    f"🏦 <b>Сводка фонда</b>\n\nСредства: {data['cash']} ₽\n"
                    f"Обязательства: {data['due']} ₽\nСвободно: {data['free']} ₽\n"
                    f"Запас: {data['runway'] or 'недостаточно данных'} мес.\n\n"
                    "/fund — подробности и запросы на согласование."
                ),
            }
        )
    results.extend(await overdue_loans(session, people, now))
    return results


async def overdue_loans(
    session: AsyncSession, people: list[FundMember], now: datetime
) -> list[dict[str, Any]]:
    """Просрочку проверяем ежедневно; повторного предупреждения по тому же займу нет."""
    results: list[dict[str, Any]] = []
    for loan in await session.scalars(
        select(FundLoan).where(FundLoan.issued, FundLoan.due_on < now.date())
    ):
        remaining = await fund_ledger.balance(session, "loan", loan.id)
        if remaining <= 0:
            continue
        employee = await session.get(Employee, loan.employee_id)
        name = escape(employee.short_name if employee else str(loan.employee_id))
        for leader in (p for p in people if p.leader):
            results.append(
                {
                    "employee_id": leader.employee_id,
                    "cycle": f"loan-overdue:{loan.id}:{loan.due_on}",
                    "text": (
                        f"⏳ <b>Срок возврата займа прошёл</b>\n\n{name}\n"
                        f"Остаток: {remaining} ₽ · вернуть до {loan.due_on:%d.%m.%Y}.\n"
                        "Откройте /fund. Закрытие месяца не блокируется."
                    ),
                }
            )
    return results


async def send_fund_notifications(bot: Bot, maker: async_sessionmaker[AsyncSession]) -> int:
    async with maker() as session:
        queue = await candidates(session)
    sent = 0
    for candidate in queue:
        async with maker() as session:
            config = await fund_config.load(session)
            if not config.module_active or not config.enabled or not config.reminders_enabled:
                break
            person = await session.get(FundMember, candidate["employee_id"])
            if person is None or not person.active:
                continue
            identity = await session.scalar(
                select(TelegramIdentity)
                .where(
                    TelegramIdentity.employee_id == person.employee_id,
                    TelegramIdentity.linked_at.is_not(None),
                    TelegramIdentity.removed_at.is_(None),
                    TelegramIdentity.dm_chat_id.is_not(None),
                )
                .order_by(TelegramIdentity.id)
                .limit(1)
            )
            if identity is None or identity.dm_chat_id is None:
                continue
            notification_id = await session.scalar(
                insert(FundNotification)
                .values(
                    employee_id=person.employee_id,
                    cycle=candidate["cycle"],
                    attempted_at=clock.now(),
                )
                .on_conflict_do_nothing()
                .returning(FundNotification.id)
            )
            chat_id = identity.dm_chat_id
            await session.commit()
            if notification_id is None:
                continue
            try:
                await bot.send_message(chat_id, candidate["text"], parse_mode="HTML")
            except Exception as exc:
                record = await session.get(FundNotification, notification_id)
                assert record is not None
                record.error = type(exc).__name__
                log.warning(
                    "fund.notification_failed", notification_id=notification_id, error=record.error
                )
            else:
                record = await session.get(FundNotification, notification_id)
                assert record is not None
                record.sent_at = clock.now()
                sent += 1
            await session.commit()
    return sent
