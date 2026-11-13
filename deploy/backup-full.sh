#!/usr/bin/env bash
# Полная копия: БД со вложениями, конфигурация запуска, шифрование и доставка вне сервера.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
root="$(pwd -P)"
key="${XTIME_BACKUP_KEY_FILE:-$root/secrets/backup.key}"
cycle="${XTIME_BACKUP_CYCLE:-$(date +%G-W%V)}"
[[ "$cycle" =~ ^[A-Za-z0-9_-]{1,60}$ ]] || { echo "Некорректный цикл копии" >&2; exit 1; }
report() { docker compose exec -T api teamtime system backup --state "$1" >/dev/null 2>&1 || true; }
failed() {
  report error
  docker compose exec -T api teamtime backup alert "$cycle" >/dev/null 2>&1 || true
  echo "Полная копия не завершена; проверьте журнал backup-full" >&2
}
trap failed ERR
if [[ ! -f "$key" ]]; then
  echo "Не настроен отдельный ключ резервной копии" >&2
  failed
  exit 1
fi
mkdir -p "$root/backups/full"
exec 9>"$root/backups/full/.lock"
flock -n 9 || exit 0
work="$(mktemp -d "$root/backups/full/.prepare.XXXXXX")"
cleanup() {
  # Удаляем только собственный временный каталог внутри проверенного пути.
  case "$work" in "$root/backups/full/.prepare."*) rm -rf -- "$work" ;; esac
}
trap cleanup EXIT
if [[ ! -f "$root/backups/full/$cycle/manifest.json" ]]; then
  mkdir "$work/input"
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$work/input/database.dump"
  for file in .env docker-compose.yml VERSION; do
    [[ ! -f "$root/$file" ]] || cp -- "$root/$file" "$work/input/$file"
  done
  docker compose exec -T api teamtime version > "$work/input/version.txt"
  docker compose run --rm --no-deps --user 0 -v "$work:/backup" -v "$key:/run/secrets/backup.key:ro" api \
    backup pack /backup/input /backup/encrypted /run/secrets/backup.key >/dev/null
  mv -- "$work/encrypted" "$root/backups/full/$cycle"
fi
docker compose run --rm --no-deps --user 0 -v "$root/backups/full/$cycle:/backup:ro" api \
  backup deliver /backup "$cycle"
report ok
echo "Полная зашифрованная копия доставлена: $cycle"
