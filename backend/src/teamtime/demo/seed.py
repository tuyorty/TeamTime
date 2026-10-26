"""Seed-генератор демо-данных: вымышленная команда и несколько недель сообщений.

Все данные проходят через тот же ``ingest``, что и сообщения из Telegram: у каждой цифры
в демо есть исходное сообщение, версии и разбор. Генератор детерминирован (``seed``),
а даты отсчитываются от «сегодня», поэтому демо всегда выглядит свежим.

Сценарии: пунктуальные и «совы», опоздания, планы «по вайбу», смена расписания посреди
недели, правки сообщений, дейлики задним числом, пропущенные дейлики, ошибки в шаблоне,
отпуск, больничный, удалёнка, непривязанный аккаунт.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.core.logging import get_logger
from teamtime.db.models import Employee, Source, TelegramIdentity
from teamtime.demo.constants import (
    DAILY_THREAD_ID,
    DEMO_CHAT_ID,
    DEMO_CHAT_TITLE,
    SCHEDULE_THREAD_ID,
)
from teamtime.demo.forum import ensure_demo_forum
from teamtime.services import manual
from teamtime.services.ingest import IncomingMessage, ingest
from teamtime.services.settings import AppSettings, load_settings, save_settings

log = get_logger(__name__)

DAY_ABBR = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
# Слоты категориальной палитры фронтенда (frontend/src/lib/colors.ts), в её порядке.
PALETTE = ("blue", "orange", "aqua", "yellow", "magenta", "green", "violet", "red")

# fmt: off
TASKS = (
    "ревью пул-реквестов", "фикс авторизации", "миграция базы на новую схему",
    "дизайн экрана отчётов", "созвон с заказчиком", "тесты для парсера", "оптимизация запросов",
    "настройка CI", "документация API", "разбор обратной связи", "прототип мобильной версии",
    "рефакторинг модуля оплаты",
    "исследование конкурентов", "подготовка демо", "обновление зависимостей", "фиксы безопасности",
    "интеграция с почтой", "доработка фильтров", "нагрузочное тестирование", "онбординг стажёра",
    "макеты для лендинга", "логирование ошибок", "разбирался с падением сборки", "экспорт в Excel",
)
# fmt: on
VIBE_NOTES = (
    "по вайбу",
    "по вайбу с 16:30 до вечера",
    "как пойдёт",
    "по вайбику(хз поеду ли)",
    "после обеда, точно не скажу",
    "может с 12",
)


@dataclass(frozen=True)
class Profile:
    """Характер вымышленного сотрудника: насколько точно он следует плану."""

    position: str
    norm_hours: int
    rate: int
    start_hour: float
    """Обычное начало дня, часы."""
    day_hours: float
    late_chance: float
    late_minutes: tuple[int, int]
    split_chance: float
    vibe_chance: float
    saturday_chance: float
    efficiency: tuple[int, int]
    miss_chance: float


# должность, норма, ставка, начало, длина дня, опоздания (шанс, минуты), разрывы, «по вайбу»,
# субботы, эффективность, шанс забыть дейлик
# fmt: off
PROFILES = (
    Profile("Бэкенд-разработчик", 160, 750, 10, 9.5, .15, (5, 40), .25, .05, .6, (85, 100), .03),
    Profile("Фронтенд-разработчица", 160, 700, 11, 8, .5, (15, 110), .2, .15, .1, (60, 95), .05),
    Profile("Дизайнер", 120, 650, 12, 7, 0.25, (10, 50), 0.15, 0.2, 0.0, (65, 100), 0.06),
    Profile("Тестировщица", 160, 550, 9, 8.5, 0.05, (3, 15), 0.1, 0.0, 0.3, (80, 100), 0.02),
    Profile("Аналитик", 80, 600, 11, 7.5, 0.3, (15, 60), 0.3, 0.1, 0.2, (75, 100), 0.04),
    Profile("DevOps-инженер", 160, 800, 8, 9.5, 0.1, (5, 25), 0.35, 0.1, 0.4, (75, 100), 0.04),
    Profile("Менеджер проекта", 120, 700, 10, 7, 0.2, (5, 30), 0.4, 0.05, 0.0, (70, 100), 0.03),
    Profile("Стажёр", 80, 400, 12, 6.5, 0.35, (10, 60), 0.1, 0.2, 0.0, (65, 95), 0.06),
)
# fmt: on


@dataclass
class Person:
    employee: Employee
    tg_id: int
    display: str
    profile: Profile
    linked: bool = True
    next_mid: list[int] = field(default_factory=lambda: [0])


def _hm(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}"


def _round5(minutes: float) -> int:
    return int(round(minutes / 5) * 5)


class Seeder:
    def __init__(self, session: AsyncSession, settings: AppSettings, seed: int = 7) -> None:
        self.session = session
        self.settings = settings
        self.rng = random.Random(seed)
        self.fake = Faker("ru_RU")
        self.fake.seed_instance(seed)
        self.message_id = 0
        self.tz = settings.tz
        self.today = clock.now().astimezone(self.tz).date()

    # --- время --------------------------------------------------------------------------

    def local(self, day: date, hours: float) -> datetime:
        h = int(hours)
        m = round((hours - h) * 60)
        moment = datetime.combine(day, time(min(h, 23), min(m, 59)), tzinfo=self.tz)
        return moment.astimezone(UTC)

    def is_past(self, moment: datetime) -> bool:
        return moment < clock.now()

    # --- люди ---------------------------------------------------------------------------

    async def people(self) -> list[Person]:
        result: list[Person] = []
        for n, profile in enumerate(PROFILES):
            female = profile.position.endswith(("ица", "ца")) or n in (2,)
            last = self.fake.last_name_female() if female else self.fake.last_name_male()
            first = self.fake.first_name_female() if female else self.fake.first_name_male()
            middle = self.fake.middle_name_female() if female else self.fake.middle_name_male()
            short = f"{last} {first[0]}.{middle[0]}."
            employee = await manual.save_employee(
                self.session,
                {
                    "full_name": f"{last} {first} {middle}",
                    "short_name": short,
                    "position": profile.position,
                    "monthly_norm_minutes": profile.norm_hours * 60,
                    "hourly_rate": Decimal(profile.rate),
                    "color": PALETTE[n % len(PALETTE)],
                    "is_active": True,
                },
                actor="seed",
            )
            # Подписи в Telegram намеренно не похожи на ФИО: матчинг идёт по строке в расписании.
            display = self.rng.choice(
                [
                    first,
                    f"{first} {last[0]}.",
                    f"🦊 {first.lower()}",
                    f"{first}_dev",
                    "🌙",
                    f"{last}",
                ]
            )
            tg_id = 7_000_000 + n * 7919
            linked = True
            self.session.add(
                TelegramIdentity(
                    telegram_user_id=tg_id,
                    username=f"demo_user_{n}",
                    display_name=display,
                    employee_id=employee.id if linked else None,
                    linked_at=clock.now() if linked else None,
                )
            )
            result.append(Person(employee, tg_id, display, profile, linked))
        await self.session.flush()
        return result

    # --- сообщения ----------------------------------------------------------------------

    async def send(
        self,
        person: Person | tuple[int, str],
        body: str,
        thread: int,
        sent_at: datetime,
        *,
        message_id: int | None = None,
        edited: bool = False,
    ) -> int:
        if message_id is None:
            self.message_id += 1
            message_id = self.message_id
        tg_id, display = person if isinstance(person, tuple) else (person.tg_id, person.display)
        await ingest(
            self.session,
            IncomingMessage(
                chat_id=DEMO_CHAT_ID,
                message_id=message_id,
                thread_id=thread,
                text=body,
                sent_at=sent_at,
                edited_at=sent_at + timedelta(minutes=self.rng.randint(3, 50)) if edited else None,
                author_id=tg_id,
                author_name=display,
                author_username=None,
                source=Source.DEMO,
                chat_title=DEMO_CHAT_TITLE,
                is_forum=True,
            ),
            self.settings,
        )
        return message_id

    # --- расписание ---------------------------------------------------------------------

    def plan_week(self, p: Person, monday: date) -> dict[int, tuple[str, tuple[int, int] | None]]:
        """День недели → (строка дня, плановый интервал в секундах или None)."""
        prof = p.profile
        plan: dict[int, tuple[str, tuple[int, int] | None]] = {}
        workdays = list(range(5)) + ([5] if self.rng.random() < prof.saturday_chance else [])
        for wd in workdays:
            if self.rng.random() < prof.vibe_chance:
                plan[wd] = (self.rng.choice(VIBE_NOTES), None)
                continue
            start_h = prof.start_hour + self.rng.choice([0, 0, 0, 0.5, 1, -1, 2])
            length = prof.day_hours + self.rng.choice([0, 0, 0, -1, 1, -2])
            start = int(start_h * 3600)
            end = int(min(start_h + max(length, 2), 23.5) * 3600)
            plan[wd] = (f"{_hm(start)} - {_hm(end)}", (start, end))
        if self.rng.random() < 0.5:
            plan[5] = plan.get(5) or ("——————", None)
        return plan

    def schedule_text(
        self, p: Person, monday: date, plan: dict[int, tuple[str, tuple[int, int] | None]]
    ) -> str:
        sat = monday + timedelta(days=5)
        dash = self.rng.choice(["-", "–", "—"])
        upper = self.rng.random() < 0.2
        lines = [f"Спринт {monday:%d.%m} {dash} {sat:%d.%m}", p.employee.short_name, ""]
        for wd in sorted(plan):
            abbr = DAY_ABBR[wd].upper() if upper else DAY_ABBR[wd]
            value = plan[wd][0].replace(" - ", f" {dash} ")
            lines.append(f"{abbr}: {value}")
        lines.append("")
        for task in self.rng.sample(TASKS, self.rng.randint(2, 4)):
            lines.append(f"- {task}")
        lines += ["", "#расписание"]
        return "\n".join(lines)

    # --- дейлик -------------------------------------------------------------------------

    def fact_for(self, p: Person, planned: tuple[int, int] | None) -> list[tuple[int, int]]:
        prof = p.profile
        if planned is None:
            start = int((prof.start_hour + self.rng.choice([1, 2, 3, 4])) * 3600)
            end = start + int(self.rng.choice([2, 3, 4, 5]) * 3600)
        else:
            start, end = planned
            if self.rng.random() < prof.late_chance:
                start += _round5(self.rng.randint(*prof.late_minutes)) * 60
            elif self.rng.random() < 0.3:
                start -= self.rng.choice([5, 10, 15]) * 60
            end += self.rng.choice([-30, -15, 0, 0, 0, 10, 20, 40, 60]) * 60
        end = min(max(end, start + 3600), 23 * 3600 + 50 * 60)
        if self.rng.random() < prof.split_chance and end - start > 4 * 3600:
            mid = start + _round5((end - start) / 120) * 60
            gap = self.rng.choice([30, 45, 60, 90]) * 60
            return [(start, mid), (mid + gap, end)]
        return [(start, end)]

    def daily_text(
        self, day: date, intervals: list[tuple[int, int]], efficiency: int | None
    ) -> str:
        sep = self.rng.choice(["; ", "; ", ", "])
        spans = sep.join(f"{_hm(a)} - {_hm(b)}" for a, b in intervals)
        eff_line = self.rng.choice(
            [
                f"Эффективность: {efficiency}%",
                f"Эффективность:  {efficiency}%",
                f"эффективность {efficiency}%",
                f"Эффективность: {efficiency}",
            ]
        )
        lines = [f"{day:%d.%m.%Y}", spans]
        if efficiency is not None:
            lines.append(eff_line)
        lines.append("")
        for task in self.rng.sample(TASKS, self.rng.randint(1, 3)):
            lines.append(f"- {task}")
        lines += ["", "#дейли"]
        return "\n".join(lines)

    # --- сценарий ----------------------------------------------------------------------

    async def run(self, weeks: int = 9) -> None:
        await ensure_demo_forum(self.session)
        people = await self.people()
        this_monday = self.today - timedelta(days=self.today.weekday())
        first_monday = this_monday - timedelta(weeks=weeks - 1)

        vacation_person = people[2]
        vacation_start = this_monday - timedelta(weeks=3)
        sick_person = people[1]
        sick_days = [this_monday - timedelta(weeks=1) + timedelta(days=d) for d in (1, 2)]

        for w in range(weeks):
            monday = first_monday + timedelta(weeks=w)
            for idx, p in enumerate(people):
                on_vacation = (
                    p is vacation_person
                    and vacation_start <= monday < vacation_start + timedelta(weeks=1)
                )
                if on_vacation:
                    continue
                plan = self.plan_week(p, monday)
                sent = self.local(monday - timedelta(days=1), self.rng.uniform(18, 23))
                if not self.is_past(sent):
                    continue
                mid = await self.send(
                    p, self.schedule_text(p, monday, plan), SCHEDULE_THREAD_ID, sent
                )
                if self.rng.random() < 0.12:
                    # Опечатку в расписании поправили редактированием сообщения.
                    plan[0] = ("12:00 - 18:00", (12 * 3600, 18 * 3600))
                    await self.send(
                        p,
                        self.schedule_text(p, monday, plan),
                        SCHEDULE_THREAD_ID,
                        sent,
                        message_id=mid,
                        edited=True,
                    )
                if self.rng.random() < 0.15:
                    # Посреди недели расписание поменяли новым сообщением — новая версия плана.
                    wd = self.rng.choice([2, 3, 4])
                    plan[wd] = ("——————", None)
                    resend = self.local(monday + timedelta(days=1), self.rng.uniform(9, 12))
                    if self.is_past(resend):
                        await self.send(
                            p, self.schedule_text(p, monday, plan), SCHEDULE_THREAD_ID, resend
                        )
                await self.week_of_dailies(
                    p, monday, plan, idx, sick_days if p is sick_person else []
                )

        # Статусы: отпуск, больничный, удалёнка, «не приду».
        await manual.set_status_range(
            self.session,
            employee_id=vacation_person.employee.id,
            start=vacation_start,
            end=vacation_start + timedelta(days=6),
            kind=StatusKind.VACATION,
            note="Отпуск, море",
            actor="seed",
        )
        for d in sick_days:
            await manual.set_status(
                self.session,
                employee_id=sick_person.employee.id,
                day=d,
                kind=StatusKind.SICK,
                note="Простуда",
                actor="seed",
            )
        for p in self.rng.sample(people[:-1], 3):
            d = (
                this_monday
                - timedelta(weeks=self.rng.randint(0, 3))
                + timedelta(days=self.rng.randint(0, 4))
            )
            if d <= self.today:
                await manual.set_status(
                    self.session,
                    employee_id=p.employee.id,
                    day=d,
                    kind=StatusKind.REMOTE,
                    actor="seed",
                )
        await manual.set_status(
            self.session,
            employee_id=people[4].employee.id,
            day=self.today,
            kind=StatusKind.ABSENT,
            note="К врачу",
            actor="seed",
        )

        await self.newcomer(this_monday)

    async def newcomer(self, this_monday: date) -> None:
        """Новый человек в чате: его ещё нет в справочнике, аккаунт не привязан — для инбокса."""
        self.session.add(
            TelegramIdentity(
                telegram_user_id=7_999_999, username="demo_newcomer", display_name="Никита 👋"
            )
        )
        await self.session.flush()
        newcomer = (7_999_999, "Никита 👋")
        saturday = this_monday + timedelta(days=5)
        sent = self.local(this_monday - timedelta(days=1), 21)
        if self.is_past(sent):
            body = (
                f"Спринт {this_monday:%d.%m} - {saturday:%d.%m}\nНовиков Н.Н.\n\n"
                "Пн: 10:00 - 18:00\nВт: 10:00 - 18:00\n\n- онбординг\n\n#расписание"
            )
            await self.send(newcomer, body, SCHEDULE_THREAD_ID, sent)
        for back in (3, 2):
            day = self.today - timedelta(days=back)
            sent = self.local(day, 19)
            if day.weekday() < 5 and self.is_past(sent):
                text = self.daily_text(day, [(10 * 3600, 18 * 3600)], 70)
                await self.send(newcomer, text, DAILY_THREAD_ID, sent)

    async def week_of_dailies(
        self,
        p: Person,
        monday: date,
        plan: dict[int, tuple[str, tuple[int, int] | None]],
        idx: int,
        sick: list[date],
    ) -> None:
        prof = p.profile
        for wd in range(7):
            day = monday + timedelta(days=wd)
            if day in sick or wd not in plan:
                continue
            line, planned = plan[wd]
            if line.startswith("—"):
                continue
            if planned is None and self.rng.random() < 0.35:
                continue  # «по вайбу» и не пришёл — бывает
            if self.rng.random() < prof.miss_chance:
                continue  # забыл дейлик
            intervals = self.fact_for(p, planned)
            efficiency = max(0, min(100, _round5(self.rng.randint(*prof.efficiency))))
            send_day = day
            r = self.rng.random()
            if r < 0.1:
                send_day = day + timedelta(days=self.rng.choice([1, 2]))  # прислал задним числом
            sent = self.local(send_day, intervals[-1][1] / 3600 + self.rng.uniform(0.05, 1.5))
            if not self.is_past(sent):
                continue
            body = self.daily_text(day, intervals, efficiency)
            edit_later = False
            if self.rng.random() < 0.04:
                body = body.replace(f"Эффективность: {efficiency}%", "").replace(
                    f"эффективность {efficiency}%", ""
                )  # забыл эффективность — увидит 🤔 и, возможно, поправит
                edit_later = self.rng.random() < 0.6
            mid = await self.send(p, body, DAILY_THREAD_ID, sent)
            if edit_later:
                await self.send(
                    p,
                    self.daily_text(day, intervals, efficiency),
                    DAILY_THREAD_ID,
                    sent,
                    message_id=mid,
                    edited=True,
                )
            elif self.rng.random() < 0.05 and efficiency is not None and efficiency <= 90:
                fixed = self.daily_text(day, intervals, efficiency + 10)
                await self.send(p, fixed, DAILY_THREAD_ID, sent, message_id=mid, edited=True)


async def clear_all(session: AsyncSession) -> None:
    await session.execute(
        text(
            "TRUNCATE audit_log, daily_tasks, daily_intervals, dailies, sprint_tasks, plan_days, "
            "schedule_plans, parse_results, raw_message_versions, raw_messages, day_statuses, "
            "topic_bindings, bot_chats, telegram_identities, employees RESTART IDENTITY CASCADE"
        )
    )


async def seed_demo(
    session: AsyncSession,
    *,
    weeks: int = 9,
    seed: int = 7,
    force: bool = False,
    if_empty: bool = False,
) -> bool:
    """Загрузить демо. Возвращает False, если пропущено (``if_empty`` и данные уже есть)."""
    existing = await session.scalar(select(func.count()).select_from(Employee)) or 0
    if existing and if_empty:
        return False
    if existing and not force:
        raise RuntimeError(
            "В базе уже есть сотрудники: используйте --force, чтобы заменить их демо"
        )
    if force:
        await clear_all(session)
    settings = await load_settings(session)
    if not settings.holidays:
        settings.holidays = [date(2026, 11, 4), date(2026, 12, 31), date(2027, 1, 1)]
        await save_settings(session, settings)
    await Seeder(session, settings, seed).run(weeks)
    log.info("demo.seeded", weeks=weeks, seed=seed)
    return True
