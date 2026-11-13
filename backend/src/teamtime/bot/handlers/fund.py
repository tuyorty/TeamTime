"""Личные финансы: просмотр, пошаговый ввод и явное подтверждение каждого факта."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.duration import format_hm
from teamtime.calc.fund import START, month_start, next_month
from teamtime.core import clock
from teamtime.db.fund import FundMember
from teamtime.db.fund_operations import (
    FundAdjustment,
    FundBasket,
    FundClaim,
    FundObligation,
    FundOperation,
    FundTimeRequest,
)
from teamtime.db.models import BotDraft, Employee
from teamtime.services import fund as access
from teamtime.services import fund_bot, fund_config, fund_ledger, fund_report, team_auth
from teamtime.services.settings import AppSettings

router = Router(name="fund")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class FinanceEntry(StatesGroup):
    value = State()
    text = State()


class Fin(CallbackData, prefix="fn"):
    action: str
    month: str
    value: int = 0


async def stop_disabled_entry(message: Message, session: AsyncSession, state: FSMContext) -> bool:
    """Отключённый мастер не перехватывает дальнейшие обычные сообщения сотрудника."""
    if (await fund_config.load(session)).module_active:
        return False
    from teamtime.bot.keyboards import reply_menu

    await state.clear()
    await message.answer(
        "Модуль фонда отключён администратором. Ввод остановлен; выберите действие в меню.",
        reply_markup=reply_menu(),
    )
    return True


def key(month: date) -> str:
    return month.strftime("%Y%m")


def parse_month(value: str) -> date:
    try:
        return date(int(value[:4]), int(value[4:]), 1)
    except ValueError as exc:
        raise access.FundError("Неверный месяц", 422) from exc


def cash(value: Any) -> str:
    from decimal import Decimal

    return f"{Decimal(str(value)):,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def navigation(month: date) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    prev = date(month.year - (month.month == 1), 12 if month.month == 1 else month.month - 1, 1)
    if prev >= START:
        kb.button(text="‹ Предыдущий месяц", callback_data=Fin(action="menu", month=key(prev)))
    kb.button(
        text="Следующий месяц ›", callback_data=Fin(action="menu", month=key(next_month(month)))
    )
    kb.adjust(2)
    return kb


async def menu(message: Message, session: AsyncSession, user: int, month: date) -> None:
    person = await access.telegram_member(session, user)
    kb = navigation(month)
    for action, label in [
        ("me", "💰 Мой расчёт"),
        ("people", "👥 Расчёт команды"),
        ("receipt", "Получил выплату"),
        ("free", "Написать одним сообщением"),
        ("sources", "Полнота выплат"),
        ("claim", "Расход за свой счёт"),
        ("time", "Отсутствие / опоздание"),
        ("correction", "Исправить данные"),
        ("treasury", "Остатки фонда"),
        ("operations", "Операции и обязательства"),
        ("reconcile", "Сверить свою корзину"),
    ]:
        kb.button(text=label, callback_data=Fin(action=action, month=key(month)))
    if person.leader:
        for action, label in [
            ("review", "Запросы на согласование"),
            ("bonus", "Назначить премию"),
            ("loan", "Одобрить заём"),
        ]:
            kb.button(text=label, callback_data=Fin(action=action, month=key(month)))
    kb.adjust(2)
    await session.commit()
    await message.answer(
        (
            f"💼 <b>Финансы · {month:%m.%Y}</b>\n\nВыберите действие. "
            f"Выплаты источников указывайте фактически полученные, "
            f"на руки."
        ),
        reply_markup=kb.as_markup(),
    )


@router.message(Command("login"))
async def login(message: Message, command: CommandObject) -> None:
    code = command.args or ""
    if len(code) != 16 or not all(c.isalnum() or c in "-_" for c in code):
        await message.answer(
            "Откройте xTime в браузере и нажмите «Получить команду "
            "входа». Отправьте выданную команду сюда."
        )
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Это мой вход — подтвердить", callback_data=f"flog:{code}")
    await message.answer(
        (
            "🔐 <b>Вход в xTime</b>\n\nПодтвердите, если вы сами "
            "только что запросили вход в браузере. Ваши полномочия "
            "будут проверены по привязке Telegram."
        ),
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("flog:"))
async def login_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        name = await team_auth.confirm_login(
            session, (callback.data or "")[5:], callback.from_user.id
        )
        await session.commit()
        await callback.message.answer(
            f"✅ Вход подтверждён: <b>{escape(name)}</b>. Вернитесь в браузер."
        )
    except access.FundError as exc:
        await session.rollback()
        await callback.message.answer(escape(str(exc)))


@router.message(Command("fund", "finance"))
@router.message(F.text == "💼 Финансы")
async def start(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    if not message.from_user:
        return
    await state.clear()
    try:
        await menu(
            message,
            session,
            message.from_user.id,
            max(START, month_start(clock.now().astimezone(settings.tz).date())),
        )
    except access.FundError as exc:
        await message.answer(escape(str(exc)))


async def show_report(
    message: Message, session: AsyncSession, user: int, month: date, employee: int
) -> None:
    actor = await access.telegram_member(session, user)
    result = await fund_report.report(session, actor.employee_id, month)
    row = next((r for r in result["rows"] if r["employee"]["id"] == employee), None)
    if row is None:
        raise access.FundError("Участник не найден в этом месяце", 404)
    lines = [
        f"💰 <b>{escape(row['employee']['name'])} · {month:%m.%Y}</b>",
        "Закрытый расчёт" if result["closed"] else "Предварительный расчёт",
        "",
        f"Норма: <b>{format_hm(row['norm_sec'])}</b>",
        f"Эффективные часы: <b>{format_hm(row['effective_sec'])}</b>",
        f"Штрафное время: <b>{format_hm(row['penalty_sec'])}</b>",
        f"Зачтено: <b>{format_hm(row['credited_sec'])}</b>",
    ]
    amounts = row["amounts"]
    if amounts:
        for field, label in [
            ("salary", "Начислено за время"),
            ("bonus", "Премии"),
            ("correction", "Корректировки"),
            ("received", "Получено из источников"),
            ("overpayment_in", "Переплата на начало"),
            ("offset", "Зачёт переплаты"),
            ("overpayment_out", "Переплата на конец"),
            ("supplement", "Доплата фонда"),
            ("compensation", "Компенсации"),
            ("paid", "Погашено обязательств"),
            ("due", "Остаток к выплате"),
        ]:
            lines.append(f"{label}: <b>{cash(amounts[field])}</b>")
    if row["blockers"]:
        lines += ["", "⚠️ <b>Нужно уточнить</b>"]
        lines += ["• " + escape(b["message"]) for b in row["blockers"][:8]]
        if len(row["blockers"]) > 8:
            lines.append(f"Ещё вопросов: {len(row['blockers']) - 8}. Подробности — в xTime.")
    kb = InlineKeyboardBuilder()
    kb.button(text="‹ Финансы", callback_data=Fin(action="menu", month=key(month)))
    await session.commit()
    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


async def prompt(message: Message, row: BotDraft, state: FSMContext) -> None:
    p = row.payload
    kb = InlineKeyboardBuilder()
    if row.submitted_at:
        await state.clear()
        await message.answer("✅ " + escape(str(p["result"])))
        return
    await state.set_state(FinanceEntry.value)
    await state.update_data(fund_draft=row.id)
    if p["step"] == len(p["fields"]):
        lines = [f"🧾 <b>Проверьте перед сохранением · {p['values']['month'][:7]}</b>", ""]
        for f in p["fields"]:
            value = p["values"][f["name"]]
            if isinstance(f.get("options"), dict):
                value = f["options"].get(str(value), value)
            displayed = escape(str(value if value is not None else "Пересчитать"))
            lines.append(f"{escape(f['label'])}: <b>{displayed}</b>")
        kb.button(text="Подтвердить", callback_data=f"fsubmit:{row.id}")
        text = "\n".join(lines)
    else:
        step = p["fields"][p["step"]]
        text = (
            f"<b>Шаг {p['step'] + 1} из {len(p['fields'])} · "
            f"{p['values']['month'][:7]}</b>\n\n{escape(step['label'])}"
        )
        options = step.get("options", [])
        options = list(options.items()) if isinstance(options, dict) else [(s, s) for s in options]
        for index, (_, label) in enumerate(options[:70]):
            kb.button(text=str(label)[:60], callback_data=f"fvalue:{row.id}:{p['step']}:{index}")
        if step.get("default"):
            kb.button(
                text=f"Сегодня · {step['default']}", callback_data=f"fvalue:{row.id}:{p['step']}:d"
            )
    kb.button(text="Отмена", callback_data=f"fcancel:{row.id}")
    kb.adjust(1)
    await send_parts(message, text, kb)


async def send_parts(message: Message, text: str, kb: InlineKeyboardBuilder) -> None:
    """Длинная карточка сохраняет все поля и подтверждение только в последней части."""
    # Подтверждение прикреплено к последней части; ни одно поле не обрезается молча.
    chunks: list[str] = [""]
    for line in text.split("\n"):
        if len(line) > 3500:
            raise access.FundError("Слишком длинное поле для предпросмотра; сократите описание")
        if len(chunks[-1]) + len(line) + 1 > 3500:
            chunks.append("")
        chunks[-1] += line + "\n"
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk, reply_markup=kb.as_markup() if index == len(chunks) - 1 else None
        )


@router.callback_query(Fin.filter())
async def action(
    callback: CallbackQuery, callback_data: Fin, session: AsyncSession, state: FSMContext
) -> None:
    if not isinstance(callback.message, Message):
        return
    msg, user, cb = callback.message, callback.from_user.id, callback_data
    model: Any
    try:
        actor = await access.telegram_member(session, user)
        month = parse_month(cb.month)
        if cb.action == "menu":
            await state.clear()
            await menu(msg, session, user, month)
        elif cb.action == "free":
            await state.set_state(FinanceEntry.text)
            await state.update_data(fund_month=str(month))
            await msg.answer(
                f"<b>Черновик за {month:%m.%Y}</b>\n\nНапишите об одной "
                f"полученной выплате или одном расходе. Укажите сумму "
                f"и дату. Перед сохранением я покажу данные для проверки.\n\nУсловия "
                f"оплаты меняет руководитель."
            )
        elif cb.action in {"me", "person"}:
            await show_report(msg, session, user, month, cb.value or actor.employee_id)
        elif cb.action == "people":
            people = await session.scalars(
                select(Employee)
                .join(FundMember, FundMember.employee_id == Employee.id)
                .order_by(Employee.id)
            )
            kb = InlineKeyboardBuilder()
            for person in people:
                kb.button(
                    text=person.short_name,
                    callback_data=Fin(action="person", month=cb.month, value=person.id),
                )
            kb.adjust(2)
            await msg.answer(f"<b>Расчёт команды · {month:%m.%Y}</b>", reply_markup=kb.as_markup())
        elif cb.action == "treasury":
            data = await fund_ledger.treasury(session, actor.employee_id)
            text = "🏦 <b>Фонд сейчас</b>\n\n" + "\n".join(
                f"{escape(b['name'])}: <b>{cash(b['balance'])}</b>" for b in data["baskets"]
            )
            text += (
                f"\n\nДеньги фонда: {cash(data['cash'])}\nОбязательства: "
                f"{cash(data['due'])}\nСвободно: <b>{cash(data['free'])}</b>\nЗапас "
                f"в месяцах: {data['runway'] or 'недостаточно данных'}"
            )
            await msg.answer(text)
        elif cb.action == "sources":
            data = await fund_report.report(session, actor.employee_id, month)
            row = next((r for r in data["rows"] if r["employee"]["id"] == actor.employee_id), None)
            if row is None:
                raise access.FundError("Нет участия в этом месяце")
            for source in row["sources"]:
                kb = InlineKeyboardBuilder()
                if not data["closed"]:
                    # Сумма и версия закреплены в одноразовом черновике, а не прочитаны после клика.
                    from uuid import uuid4

                    draft = BotDraft(
                        id=str(uuid4()),
                        employee_id=actor.employee_id,
                        user_id=user,
                        payload={
                            "type": "source",
                            "month": str(month),
                            "source": source["name"],
                            "expected_total": source["amount"],
                            "expected_version": source["version"],
                        },
                    )
                    session.add(draft)
                    await session.commit()
                    kb.button(text="Всё получено", callback_data=f"fsource:{draft.id}:yes")
                    kb.button(text="Жду ещё", callback_data=f"fsource:{draft.id}:no")
                    kb.adjust(2)
                completion = (
                    "✅ Полнота подтверждена"
                    if source["state"] == "complete"
                    else "Ожидается подтверждение полноты"
                )
                await msg.answer(
                    (
                        f"<b>{escape(source['name'])} · {month:%m.%Y}</b>\nСохранено: "
                        f"{cash(source['amount'])}\n{completion}"
                    ),
                    reply_markup=kb.as_markup(),
                )
            if not row["sources"]:
                await msg.answer(
                    "Источники выплат не заданы в условиях. При необходимости "
                    "уточните их у руководителя."
                )
        elif cb.action == "review":
            await access.member(session, actor.employee_id, leader=True)
            kb = InlineKeyboardBuilder()
            for model, command, label in [
                (FundClaim, "claim_decide", "Расход"),
                (FundTimeRequest, "time_decide", "Время"),
                (FundAdjustment, "correction_decide", "Корректировка"),
            ]:
                for row in await session.scalars(
                    select(model).where(model.state == "pending").limit(20)
                ):
                    employee = await session.get(Employee, row.employee_id)
                    kb.button(
                        text=(
                            f"{label} #{row.id} · "
                            f"{employee.short_name if employee else row.employee_id}"
                        ),
                        callback_data=Fin(action=command, month=cb.month, value=row.id),
                    )
            kb.adjust(1)
            await msg.answer(
                "<b>Запросы на согласование</b>\nВыберите запрос для просмотра и решения.",
                reply_markup=kb.as_markup(),
            )
        elif cb.action == "operations":
            data = await fund_ledger.treasury(session, actor.employee_id)
            lines = ["<b>Невыплаченные обязательства</b>"]
            for o in data["obligations"]:
                if float(o["due"]) > 0:
                    employee = await session.get(Employee, o["employee_id"])
                    lines.append(
                        f"#{o['id']} · {escape(employee.short_name if employee else '')} "
                        f"· {o['month'][:7]} · {cash(o['due'])}"
                    )
            kb = InlineKeyboardBuilder()
            kb.button(text="Новая операция", callback_data=Fin(action="operation", month=cb.month))
            for o in await session.scalars(
                select(FundOperation)
                .where(FundOperation.state == "draft")
                .order_by(FundOperation.id)
                .limit(30)
            ):
                kb.button(
                    text=f"Операция #{o.id} · {cash(o.amount)}",
                    callback_data=Fin(action="operation_view", month=cb.month, value=o.id),
                )
            kb.adjust(1)
            await msg.answer("\n".join(lines)[:4000], reply_markup=kb.as_markup())
        elif cb.action == "operation_view":
            operation = await session.get(FundOperation, cb.value)
            if operation is None:
                raise access.FundError("Операция не найдена")
            kb = InlineKeyboardBuilder()
            if operation.state == "draft":
                kb.button(
                    text="Подтвердить факт",
                    callback_data=Fin(
                        action="operation_confirm", month=cb.month, value=operation.id
                    ),
                )
                kb.button(
                    text="Отменить",
                    callback_data=Fin(
                        action="operation_cancel", month=cb.month, value=operation.id
                    ),
                )
            if operation.kind == "loan_offset" and operation.employee_id == actor.employee_id:
                kb.button(
                    text="Согласен на зачёт займа",
                    callback_data=Fin(action="consent", month=cb.month, value=operation.id),
                )
            kb.adjust(1)
            names = {
                "contribution": "Взнос",
                "interest": "Проценты",
                "expense": "Расход фонда",
                "payment": "Выплата сотруднику",
                "transfer": "Перевод между корзинами",
                "loan_issue": "Выдача займа",
                "loan_repayment": "Возврат займа",
                "overpayment_return": "Возврат переплаты",
                "compensation_return": "Возврат компенсации",
                "loan_offset": "Зачёт займа",
                "allocate": "Распределение выплаты",
                "refund": "Возврат расхода",
                "cash_correction": "Корректировка остатка",
            }
            lines = [
                f"<b>{names.get(operation.kind, 'Операция')} #{operation.id}</b>",
                f"{operation.occurred_on:%d.%m.%Y} · <b>{cash(operation.amount)}</b>",
                {
                    "draft": "Черновик — деньги ещё не учтены",
                    "posted": "Проведена",
                    "cancelled": "Отменена",
                }[operation.state],
            ]
            for title, basket_id in (
                ("Корзина", operation.basket_id),
                ("Куда", operation.target_basket_id),
            ):
                if basket_id:
                    basket = await session.get(FundBasket, basket_id)
                    if basket:
                        lines.append(f"{title}: {escape(basket.name)}")
            if operation.employee_id:
                employee = await session.get(Employee, operation.employee_id)
                if employee:
                    lines.append(f"Участник: {escape(employee.full_name)}")
            for item in operation.details.get("allocations", []):
                obligation = await session.get(FundObligation, int(item["obligation_id"]))
                if obligation:
                    lines.append(
                        f"{obligation.month:%m.%Y} · {escape(obligation.title)}: "
                        f"{cash(item['amount'])}"
                    )
            lines.append(f"\nОснование: {escape(operation.reason)}")
            await send_parts(msg, "\n".join(lines), kb)
        elif cb.action in {"operation_confirm", "consent"}:
            async with session.begin_nested():
                if cb.action == "consent":
                    await fund_ledger.consent(session, actor.employee_id, cb.value)
                else:
                    await fund_ledger.confirm_operation(session, actor.employee_id, cb.value)
            await session.commit()
            await msg.answer(
                "✅ Согласие сохранено."
                if cb.action == "consent"
                else "✅ Операция проведена. Повторное нажатие не создаст новое движение."
            )
        else:
            async with session.begin_nested():
                draft = await fund_bot.create_draft(session, user, cb.action, month, cb.value)
                if cb.action.endswith("decide"):
                    model = {
                        "claim_decide": FundClaim,
                        "time_decide": FundTimeRequest,
                        "correction_decide": FundAdjustment,
                    }[cb.action]
                    item = await session.get(model, cb.value)
                    if item is None:
                        raise access.FundError("Запрос не найден")
                    description = getattr(item, "title", getattr(item, "reason", ""))
                    details = (
                        f"Запрос #{item.id}\n{description}\n"
                        f"Сумма: {getattr(item, 'amount', '—')}\nДаты: "
                        f"{', '.join(getattr(item, 'days', []))}"
                    )
                else:
                    details = ""
            await session.commit()
            if details:
                await msg.answer(escape(details[:3500]))
            await prompt(msg, draft, state)
    except access.FundError as exc:
        await session.rollback()
        await msg.answer("⚠️ " + escape(str(exc)))


@router.message(FinanceEntry.text, F.text, ~F.text.startswith("/"))
async def free_entry(message: Message, session: AsyncSession, state: FSMContext) -> None:
    from teamtime.core.config import get_settings
    from teamtime.services.fund_language import extract

    if not message.from_user or not message.text:
        return
    if await stop_disabled_entry(message, session, state):
        return
    try:
        await access.telegram_member(session, message.from_user.id)
        await session.commit()
        candidate = await extract(message.text, get_settings())
        month = date.fromisoformat((await state.get_data())["fund_month"])
        row = await fund_bot.create_draft(session, message.from_user.id, candidate.kind, month)
        supplied = {
            "amount": candidate.amount,
            "date": str(candidate.occurred_on) if candidate.occurred_on else None,
            "source": candidate.source,
            "title": candidate.title,
        }
        supplied = {k: v for k, v in supplied.items() if v is not None}
        fields = sorted(row.payload["fields"], key=lambda f: f["name"] in supplied)
        row.payload = {
            **row.payload,
            "fields": fields,
            "values": {**row.payload["values"], **supplied},
            "raw_text": message.text,
            "suggested_by_model": True,
            "step": 0 if any(f["name"] not in supplied for f in fields) else len(fields),
        }
        await session.commit()
        await prompt(message, row, state)
    except access.FundError as exc:
        await session.rollback()
        await message.answer("⚠️ " + escape(str(exc)))


@router.message(FinanceEntry.value, F.text, ~F.text.startswith("/"))
async def entry(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    if await stop_disabled_entry(message, session, state):
        return
    draft_id = (await state.get_data()).get("fund_draft", "")
    try:
        row = await fund_bot.answer(
            session, message.from_user.id, draft_id, message.text, f"message:{message.message_id}"
        )
        await session.commit()
        await prompt(message, row, state)
    except access.FundError as exc:
        await session.rollback()
        await message.answer("⚠️ " + escape(str(exc)))


@router.callback_query(F.data.startswith("fvalue:"))
async def entry_button(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        _, draft_id, step_index, choice = (callback.data or "").split(":")
        row = await fund_bot.owned_draft(session, callback.from_user.id, draft_id)
        if row.payload["step"] != int(step_index):
            await callback.answer("Этот шаг уже заполнен")
            return
        step = row.payload["fields"][int(step_index)]
        text = step["default"] if choice == "d" else list(step["options"])[int(choice)]
        row = await fund_bot.answer(
            session, callback.from_user.id, draft_id, text, callback.data or ""
        )
        await session.commit()
        await prompt(callback.message, row, state)
    except (access.FundError, ValueError, IndexError, KeyError) as exc:
        await session.rollback()
        await callback.message.answer("⚠️ " + escape(str(exc)))


@router.callback_query(F.data.startswith("fsubmit:"))
async def submit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        async with session.begin_nested():
            _, text = await fund_bot.submit(
                session, callback.from_user.id, (callback.data or "")[8:]
            )
        await session.commit()
        await state.clear()
        await callback.message.answer("✅ " + escape(text))
    except access.FundError as exc:
        await session.rollback()
        await callback.message.answer("⚠️ " + escape(str(exc)))


@router.callback_query(F.data.startswith("fcancel:"))
async def cancel(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        row = await fund_bot.owned_draft(session, callback.from_user.id, (callback.data or "")[8:])
        if not row.submitted_at:
            row.submitted_at = clock.now()
            row.payload = {**row.payload, "result": "Черновик отменён. Данные не изменились."}
        await session.commit()
        await state.clear()
        await callback.message.answer(escape(row.payload["result"]))
    except access.FundError as exc:
        await callback.message.answer(escape(str(exc)))


@router.callback_query(F.data.startswith("fsource:"))
async def source_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        _, draft_id, complete = (callback.data or "").split(":")
        actor = await access.telegram_member(session, callback.from_user.id)
        await access.lock(session)
        row = await session.get(BotDraft, draft_id, populate_existing=True)
        if not row or row.user_id != callback.from_user.id or row.payload.get("type") != "source":
            raise access.FundError("Карточка не найдена", 403)
        if not row.submitted_at:
            from decimal import Decimal

            p = row.payload
            await access.confirm_source(
                session,
                actor.employee_id,
                actor.employee_id,
                month=date.fromisoformat(p["month"]),
                source=p["source"],
                complete=complete == "yes",
                expected_total=Decimal(p["expected_total"]),
                expected_version=p["expected_version"],
            )
            row.submitted_at = clock.now()
        await session.commit()
        await callback.message.answer(
            "✅ Состояние поступлений сохранено. Новую выплату добавляйте отдельной записью."
        )
    except (access.FundError, ValueError) as exc:
        await session.rollback()
        await callback.message.answer("⚠️ " + escape(str(exc)))
