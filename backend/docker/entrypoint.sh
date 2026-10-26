#!/bin/sh
# Точка входа контейнера бэкенда: api | bot | любая команда teamtime.
set -eu

case "${1:-api}" in
  api)
    teamtime db upgrade
    if [ "${DEMO:-0}" = "1" ] || [ "${DEMO:-false}" = "true" ]; then
      teamtime demo seed --if-empty
    fi
    exec uvicorn teamtime.api.app:app --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips='*' --no-access-log
    ;;
  bot)
    exec teamtime bot run
    ;;
  *)
    exec teamtime "$@"
    ;;
esac
