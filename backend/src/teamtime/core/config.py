"""Настройки процесса из переменных окружения.

Здесь только то, что нужно для запуска: подключения, секреты, флаги. Бизнес-настройки
(допуск опоздания, шкала штрафа, праздники) хранятся в базе и меняются в админке,
см. ``teamtime.services.settings``.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_EPHEMERAL_KEY = secrets.token_urlsafe(32)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    database_url: str = Field(
        default="postgresql+asyncpg://teamtime:teamtime@localhost:5432/teamtime",
        description="Строка подключения SQLAlchemy (драйвер asyncpg).",
    )

    bot_token: SecretStr | None = Field(default=None, description="Токен бота от @BotFather.")
    bot_username: str | None = Field(
        default=None, description="Имя бота без @, нужно для deep link «Исправить в боте»."
    )

    telegram_proxy: str | None = Field(
        default=None,
        description="Прокси до api.telegram.org, если с сервера он недоступен напрямую: "
        "http://host:port или socks5://user:pass@host:port.",
    )

    admin_password: SecretStr | None = Field(
        default=None, description="Пароль режима админа. Пусто — режим админа выключен."
    )
    session_secret: SecretStr | None = Field(
        default=None,
        description="Ключ подписи cookie-сессии. Не задан — случайный на каждый запуск "
        "(сессии админа сбрасываются при перезапуске).",
    )
    session_max_age_hours: int = 12

    default_timezone: str = Field(
        default="Asia/Yekaterinburg",
        description="Часовой пояс по умолчанию; в работе используется значение из настроек БД.",
    )
    public_url: str = Field(
        default="http://localhost:8080",
        description="Адрес сайта в локальной сети; используется при установке и диагностике.",
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    demo: bool = Field(default=False, description="Демо-режим: эмулятор чата, пароль админа demo.")
    demo_now: datetime | None = Field(
        default=None,
        description="Заморозить «сейчас» (ISO с часовым поясом) — для скриншотов и e2e на демо.",
    )

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    @property
    def signing_key(self) -> str:
        """Ключ подписи сессий. Без SESSION_SECRET — случайный на процесс, а не известная
        строка из репозитория: иначе любой мог бы подписать себе cookie админа."""
        if self.session_secret and self.session_secret.get_secret_value():
            return self.session_secret.get_secret_value()
        return _EPHEMERAL_KEY

    @property
    def password_fingerprint(self) -> str:
        """Отпечаток пароля админа: смена пароля делает недействительными все сессии."""
        import hashlib

        password = self.admin_password.get_secret_value() if self.admin_password else ""
        return hashlib.sha256(f"xtime-session:{password}".encode()).hexdigest()[:16]

    @property
    def admin_enabled(self) -> bool:
        return self.demo or bool(self.admin_password and self.admin_password.get_secret_value())

    def check_admin_password(self, candidate: str) -> bool:
        import hmac

        expected = (
            "demo"
            if self.demo and not self.admin_password
            else (self.admin_password.get_secret_value() if self.admin_password else "")
        )
        if not expected:
            return False
        return hmac.compare_digest(candidate.encode(), expected.encode())


@lru_cache
def get_settings() -> Settings:
    return Settings()
