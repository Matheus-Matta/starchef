#!/usr/bin/env bash
# Backend dedicado ao teste de carga (Linux/macOS/Git Bash).
# Banco proprio + throttle praticamente desligado: o teste mede o sistema, nao o DRF.
set -euo pipefail

PORT="${1:-8001}"
DATABASE="${2:-db_loadtest.sqlite3}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

export DJANGO_ENV=development
# Postgres quando POSTGRES_HOST estiver definido. SQLite serializa escrita e
# devolve "database is locked" (500) sob concorrencia — util para conhecer o
# teto do ambiente de dev, inutil para medir o codigo.
if [ -n "${POSTGRES_HOST:-}" ]; then
  export USE_SQLITE_DATABASE=False
  echo "Banco: Postgres em $POSTGRES_HOST"
else
  export USE_SQLITE_DATABASE=True
  export SQLITE_DB_NAME="$DATABASE"
  echo "Banco: SQLite $DATABASE (perfis pesado/extremo pedem Postgres)"
fi
export THROTTLE_RATE_ANON=1000000/min
export THROTTLE_RATE_USER=10000000/hour
export THROTTLE_RATE_LOGIN=100000/min
export THROTTLE_RATE_TOKEN_REFRESH=100000/min
export THROTTLE_RATE_DEVICE_POLL=1000000/min
export THROTTLE_RATE_CASH_APPROVAL=1000000/min
export THROTTLE_RATE_PASSWORD_RESET=100000/min

PY="$RAIZ/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$RAIZ/.venv/bin/python"

echo "Porta: $PORT"
"$PY" backend/manage.py migrate --noinput
exec "$PY" backend/manage.py runserver "0.0.0.0:$PORT" --noreload
