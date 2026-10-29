"""xTime: таблица команды из сообщений Telegram."""

import os

# В релизный образ тег попадает при сборке (make release); локально — dev.
__version__ = os.environ.get("XTIME_VERSION") or "dev"
