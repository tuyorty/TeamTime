#!/usr/bin/env bash
# Бэкап базы xTime в backups/ рядом со скриптом. Хранит последние KEEP копий (по умолчанию 14).
# Для ежедневного бэкапа в 03:00 — строка в crontab (crontab -e):
#   0 3 * * * /opt/xtime/backup.sh >> /opt/xtime/backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")"
KEEP="${KEEP:-14}"
mkdir -p backups
file="backups/xtime-$(date +%Y-%m-%d_%H%M).dump"

docker compose exec -T db pg_dump -U xtime -d xtime --format=custom > "$file.part"
mv "$file.part" "$file"
echo "$(date '+%F %T') бэкап: $file ($(du -h "$file" | cut -f1))"

ls -1t backups/xtime-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm -f
