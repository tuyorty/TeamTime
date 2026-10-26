# xTime на сервере

Архив релиза содержит всё нужное: образы приложения и PostgreSQL, `docker-compose.yml`
и скрипты. Серверу не нужен доступ к Docker Hub, PyPI и npm. Наружу нужен только
исходящий HTTPS до `api.telegram.org` для бота. Входящие подключения из интернета,
белый IP и webhook не нужны: бот сам опрашивает Telegram.

## Что нужно на сервере

- Linux с Docker Engine и плагином `docker compose` 2.20+.
- Свободный порт для сайта (по умолчанию 8090).
- Исходящий доступ к `api.telegram.org:443`, напрямую или через прокси.

## Первая установка

С Mac разработчика, из корня репозитория (нужен SSH-доступ к серверу):

```
make deploy HOST=user@сервер
```

Или вручную: собрать архив `make release`, скопировать `dist/xtime-<версия>.tar.gz`
на сервер и там:

```
tar -xzf xtime-<версия>.tar.gz
sudo xtime-<версия>/install.sh /opt/xtime
```

Первый запуск создаёт `/opt/xtime/.env` и останавливается. Заполните в нём `BOT_TOKEN`,
`BOT_USERNAME` и `ADMIN_PASSWORD`, при необходимости `WEB_PORT`, и запустите ещё раз:

```
sudo /opt/xtime/install.sh /opt/xtime
```

Скрипт проверит порт и связь с Telegram, поднимет базу, API, сайт и бота и покажет адрес сайта.

## Обновление

Тот же `make deploy HOST=…` или `install.sh` из нового архива. `.env`, база и бэкапы
остаются на месте, миграции применяются при старте.

## Если Telegram недоступен

`install.sh` проверяет связь командой `teamtime bot check`. Если в сети закрыт
`api.telegram.org`, укажите прокси в `.env` и перезапустите `install.sh`:

```
TELEGRAM_PROXY=socks5://user:pass@10.0.0.5:1080   # или http://host:port
```

Проверить вручную: `docker compose run --rm --no-deps api bot check`.

## Бэкапы

```
/opt/xtime/backup.sh                     # дамп в /opt/xtime/backups, хранятся 14 последних
```

Ежедневно в 03:00 — строка в `crontab -e`:

```
0 3 * * * /opt/xtime/backup.sh >> /opt/xtime/backups/backup.log 2>&1
```

Восстановление из дампа (текущие данные заменятся):

```
cd /opt/xtime
docker compose stop api bot web
docker compose exec -T db pg_restore -U xtime -d xtime --clean --if-exists < backups/<файл>.dump
docker compose up -d
```

## Полезное

```
cd /opt/xtime
docker compose ps                       # состояние
docker compose logs -f api bot          # логи
docker compose down                     # остановить, база сохранится
docker compose down -v                  # остановить и удалить базу — всё с нуля
docker compose exec api teamtime import telegram /path/result.json   # импорт истории чата
```

Файл экспорта для импорта сначала положите в контейнер или загрузите через «Админка → Импорт».
