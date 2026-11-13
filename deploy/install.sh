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

# RELEASE_VERSION обозначает подготовленный пакет, VERSION — успешно запущенный выпуск.
# Отдельный маркер нужен после первого запуска: пользователь заполняет .env и повторяет
# установку уже из DEST, где ещё нет успешно установленной версии.
version_file="$SRC/RELEASE_VERSION"
[ -f "$version_file" ] || version_file="$SRC/VERSION"
[ -f "$version_file" ] || die "Нет VERSION пакета: запустите install.sh из архива релиза"
release_version="$(tr -d '\r\n' < "$version_file")"
[[ "$release_version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] \
  || die "Некорректная версия пакета"
backend_image="xtime-backend:$release_version"
# Переменная процесса имеет приоритет над старым XTIME_TAG в .env. Постоянную настройку
# обновляем только после проверки новой версии API, вместе с маркером VERSION.
compose() { XTIME_TAG="$release_version" docker compose "$@"; }

# --- 1. Docker ------------------------------------------------------------------------------
command -v docker >/dev/null || die "Нет Docker. Установите Docker Engine: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || die "Нет плагина docker compose (нужна версия 2.20+)"
docker info >/dev/null 2>&1 || die "Docker недоступен этому пользователю: запустите через sudo или добавьте себя в группу docker"

# --- 2. Файлы -------------------------------------------------------------------------------
mkdir -p "$DEST/backups"
DEST="$(cd "$DEST" && pwd)"
if [ "$SRC" != "$DEST" ]; then
  cp "$SRC/docker-compose.yml" "$SRC/.env.example" "$SRC/install.sh" "$SRC/backup.sh" "$SRC/README.md" "$DEST/"
  [ -f "$SRC/xtime-tg-tunnel.service" ] && cp "$SRC/xtime-tg-tunnel.service" "$DEST/"
  for extra in backup-full.sh xtime-backup-full.service xtime-backup-full.timer UPDATE.md MULTIPLE_CHATS.md FINANCE.md FUND.md FUND_BACKUP.md LEGACY_IMPORT.md; do
    [ ! -f "$SRC/$extra" ] || cp "$SRC/$extra" "$DEST/"
  done
fi
printf '%s\n' "$release_version" > "$DEST/RELEASE_VERSION"
chmod +x "$DEST/install.sh" "$DEST/backup.sh"
[ ! -f "$DEST/backup-full.sh" ] || chmod +x "$DEST/backup-full.sh"
cd "$DEST"

# --- 3. Образы ------------------------------------------------------------------------------
if [ -f "$SRC/images.tar.gz" ]; then
  say "Загружаю образы $release_version…"
  gunzip -c "$SRC/images.tar.gz" | docker load
fi
for image in "$backend_image" "xtime-web:$release_version" "xtime-db:$release_version"; do
  docker image inspect "$image" >/dev/null 2>&1 || die "Нет образа $image: запустите install.sh из распакованного архива релиза"
done

# --- 4. .env --------------------------------------------------------------------------------
random() { docker run --rm --network none --entrypoint python "$backend_image" -c "import secrets; print(secrets.token_urlsafe($1))"; }
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

case "$(get_env DEMO)" in
  1|true|True|TRUE) die "В .env включён DEMO: это режим с вымышленными данными, паролем demo и открытым эмулятором чата. Уберите DEMO из рабочего .env" ;;
esac
admin_pw="$(get_env ADMIN_PASSWORD)"
if [ -z "$admin_pw" ]; then
  warn "ADMIN_PASSWORD пуст: режим админа на сайте будет выключен"
elif [ "${#admin_pw}" -lt 12 ]; then
  warn "ADMIN_PASSWORD короче 12 символов: сайт открыт всей сети, возьмите пароль длиннее"
fi

# --- 5. Порт --------------------------------------------------------------------------------
port="$(get_env WEB_PORT)"; port="${port:-8090}"
ours="$(compose ps -q web 2>/dev/null || true)"
if [ -z "$ours" ] && command -v ss >/dev/null && ss -ltnH "sport = :$port" | grep -q .; then
  die "Порт $port уже занят другим сервисом. Укажите свободный в WEB_PORT в .env"
fi

# --- 6. Telegram ----------------------------------------------------------------------------
services=(db api web)
if [ -z "$(get_env BOT_TOKEN)" ]; then
  warn "BOT_TOKEN пуст: запускаю только сайт, без бота"
else
  say "Проверяю связь с Telegram…"
  if docker run --rm --env-file .env --entrypoint teamtime "$backend_image" bot check; then
    services+=(bot)
  else
    warn "Бот не запущен. Если api.telegram.org закрыт в сети, укажите TELEGRAM_PROXY в .env и запустите install.sh ещё раз"
  fi
fi

# --- 7. Запуск ------------------------------------------------------------------------------
say "Запускаю: ${services[*]}"
compose up -d --remove-orphans "${services[@]}"
[[ " ${services[*]} " == *" bot "* ]] || compose stop bot >/dev/null 2>&1 || true

say "Жду, пока поднимется API (миграции применяются сами)…"
api_id="$(compose ps -q api)"
[ -n "$api_id" ] || die "Контейнер API не создан. Логи: cd $DEST && docker compose logs api"
for _ in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$api_id" 2>/dev/null || true)" = "healthy" ] && break
  sleep 2
done
[ "$(docker inspect -f '{{.State.Health.Status}}' "$api_id" 2>/dev/null || true)" = "healthy" ] \
  || die "API не поднялся. Логи: docker compose -f $DEST/docker-compose.yml logs api"

actual_version="$(compose exec -T api teamtime version)"
[ "$actual_version" = "$release_version" ] \
  || die "API запущен с версией $actual_version вместо $release_version. Обновление не подтверждено"
set_env XTIME_TAG "$release_version"
printf '%s\n' "$release_version" > VERSION.tmp
mv VERSION.tmp VERSION
echo
say "xTime $(cat VERSION 2>/dev/null || true) работает: $(get_env PUBLIC_URL)"
echo "  логи:     cd $DEST && docker compose logs -f api bot"
echo "  бэкап:    $DEST/backup.sh"
echo "  стоп:     cd $DEST && docker compose down   (база сохранится)"
