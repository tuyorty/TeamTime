#!/usr/bin/env bash
# Установка и обновление xTime на сервере из распакованного архива релиза.
#
#   ./install.sh                 # в /opt/xtime
#   ./install.sh /srv/xtime      # в другую папку
#
# Первый запуск создаёт .env и просит заполнить BOT_TOKEN и ADMIN_PASSWORD. Повторный запуск
# с новым архивом — обновление: .env, база и бэкапы остаются на месте.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-/opt/xtime}"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. Docker ------------------------------------------------------------------------------
command -v docker >/dev/null || die "Нет Docker. Установите Docker Engine: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || die "Нет плагина docker compose (нужна версия 2.20+)"
docker info >/dev/null 2>&1 || die "Docker недоступен этому пользователю: запустите через sudo или добавьте себя в группу docker"

# --- 2. Файлы -------------------------------------------------------------------------------
mkdir -p "$DEST/backups"
if [ "$SRC" != "$DEST" ]; then
  cp "$SRC/docker-compose.yml" "$SRC/.env.example" "$SRC/install.sh" "$SRC/backup.sh" "$SRC/README.md" "$DEST/"
  [ -f "$SRC/VERSION" ] && cp "$SRC/VERSION" "$DEST/"
fi
chmod +x "$DEST/install.sh" "$DEST/backup.sh"
cd "$DEST"

# --- 3. Образы ------------------------------------------------------------------------------
if [ -f "$SRC/images.tar.gz" ]; then
  say "Загружаю образы $(cat "$SRC/VERSION" 2>/dev/null || true)…"
  gunzip -c "$SRC/images.tar.gz" | docker load
fi
for image in xtime-backend:current xtime-web:current xtime-db:current; do
  docker image inspect "$image" >/dev/null 2>&1 || die "Нет образа $image: запустите install.sh из распакованного архива релиза"
done

# --- 4. .env --------------------------------------------------------------------------------
random() { docker run --rm --entrypoint python xtime-backend:current -c "import secrets; print(secrets.token_urlsafe($1))"; }
set_env() { # set_env KEY VALUE — заменить или дописать строку
  if grep -q "^$1=" .env; then
    sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}
get_env() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2- || true; }

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  set_env POSTGRES_PASSWORD "$(random 24)"
  set_env SESSION_SECRET "$(random 32)"
  set_env PUBLIC_URL "http://${ip:-localhost}:$(get_env WEB_PORT)"
  say "Создан $DEST/.env"
  echo "Заполните в нём BOT_TOKEN, BOT_USERNAME и ADMIN_PASSWORD, затем снова запустите:"
  echo "  $DEST/install.sh $DEST"
  exit 0
fi
# Старые .env без новых ключей тоже должны работать.
[ -n "$(get_env POSTGRES_PASSWORD)" ] || set_env POSTGRES_PASSWORD "$(random 24)"
[ -n "$(get_env SESSION_SECRET)" ] || set_env SESSION_SECRET "$(random 32)"

[ -n "$(get_env ADMIN_PASSWORD)" ] || warn "ADMIN_PASSWORD пуст: режим админа на сайте будет выключен"

# --- 5. Порт --------------------------------------------------------------------------------
port="$(get_env WEB_PORT)"; port="${port:-8090}"
ours="$(docker compose ps -q web 2>/dev/null || true)"
if [ -z "$ours" ] && command -v ss >/dev/null && ss -ltnH "sport = :$port" | grep -q .; then
  die "Порт $port уже занят другим сервисом. Укажите свободный в WEB_PORT в .env"
fi

# --- 6. Telegram ----------------------------------------------------------------------------
services=(db api web)
if [ -z "$(get_env BOT_TOKEN)" ]; then
  warn "BOT_TOKEN пуст: запускаю только сайт, без бота"
else
  say "Проверяю связь с Telegram…"
  if docker run --rm --env-file .env --entrypoint teamtime xtime-backend:current bot check; then
    services+=(bot)
  else
    warn "Бот не запущен. Если api.telegram.org закрыт в сети, укажите TELEGRAM_PROXY в .env и запустите install.sh ещё раз"
  fi
fi

# --- 7. Запуск ------------------------------------------------------------------------------
say "Запускаю: ${services[*]}"
docker compose up -d --remove-orphans "${services[@]}"
[[ " ${services[*]} " == *" bot "* ]] || docker compose stop bot >/dev/null 2>&1 || true

say "Жду, пока поднимется API (миграции применяются сами)…"
for _ in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)")" = "healthy" ] && break
  sleep 2
done
[ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)")" = "healthy" ] \
  || die "API не поднялся. Логи: docker compose -f $DEST/docker-compose.yml logs api"

docker image prune -f >/dev/null 2>&1 || true
echo
say "xTime $(cat VERSION 2>/dev/null || true) работает: $(get_env PUBLIC_URL)"
echo "  логи:     cd $DEST && docker compose logs -f api bot"
echo "  бэкап:    $DEST/backup.sh"
echo "  стоп:     cd $DEST && docker compose down   (база сохранится)"
