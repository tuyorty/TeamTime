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

### SSH-туннель через свой сервер

Если прокси нет, но есть сервер с доступом к Telegram и SSH-входом на него, туннель
поднимается на этом сервере без установки чего-либо на релее. Служба работает
от обычного пользователя, у которого лежит ключ. Шаблон службы —
`xtime-tg-tunnel.service`, шаги установки в его шапке. Коротко:

```
# ключ ~/.ssh/xtime_tg у обычного пользователя, .pub — в authorized_keys на релее
sed -e 's|LOCAL_USER|user|' -e 's|KEY_PATH|/home/user/.ssh/xtime_tg|' \
  -e 's|USER@RELAY|user@relay.example|' /opt/xtime/xtime-tg-tunnel.service \
  | sudo tee /etc/systemd/system/xtime-tg-tunnel.service >/dev/null
sudo systemctl daemon-reload && sudo systemctl enable --now xtime-tg-tunnel
curl --socks5-hostname 172.17.0.1:1080 -sI https://api.telegram.org | head -1
```

В `.env`: `TELEGRAM_PROXY=socks5://172.17.0.1:1080`, затем `install.sh`. Адрес Telegram
определяется на стороне релея, так что DNS этого сервера не мешает. Если `curl` отвечает,
а `bot check` нет, файрвол не пускает контейнеры к туннелю:
`sudo ufw allow from 172.16.0.0/12 to any port 1080 proto tcp`.

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
