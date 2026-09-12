#!/usr/bin/env bash
# Alvo da carga em modo PRODUÇÃO, na máquina local (Docker Desktop):
#   1. Postgres 16 num container SEPARADO (rede externa `starchef-loadtest`);
#   2. backend gunicorn/UvicornWorker + Redis pelo docker/loadtest/docker-compose.yml;
#   3. banco zerado e semeado com `seed_demo`.
#
#   bash loadtest/scripts/start_prod_target.sh            # porta 8012
#   GUNICORN_WORKERS=8 bash loadtest/scripts/start_prod_target.sh 8012
#   bash loadtest/scripts/start_prod_target.sh --down      # derruba tudo
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$RAIZ/docker/loadtest/docker-compose.yml"
REDE="starchef-loadtest"
PG="starchef-pg-loadtest"
PG_PORT="${PG_PORT:-5433}"

if [ "${1:-}" = "--down" ]; then
  docker compose -f "$COMPOSE" down -v --remove-orphans || true
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker network rm "$REDE" >/dev/null 2>&1 || true
  echo "alvo de producao derrubado"
  exit 0
fi

export LOADTEST_PORT="${1:-8012}"
# pip atrás de proxy com TLS interceptado (ver Dockerfile). Vazio = verifica.
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.org files.pythonhosted.org}"

docker network inspect "$REDE" >/dev/null 2>&1 || docker network create "$REDE" >/dev/null

# 1) Postgres separado. Zerado a cada subida: a carga precisa de ponto de
#    partida conhecido, e a semente do harness é determinística.
docker rm -f "$PG" >/dev/null 2>&1 || true
docker run -d --name "$PG" --network "$REDE" \
  -e POSTGRES_DB=starchef_loadtest -e POSTGRES_USER=starchef \
  -e POSTGRES_PASSWORD=loadtest-only-password \
  -p "127.0.0.1:${PG_PORT}:5432" \
  postgres:16-alpine >/dev/null
echo "Postgres: container $PG (host 127.0.0.1:${PG_PORT})"
for _ in $(seq 1 30); do
  if docker exec "$PG" pg_isready -U starchef -d starchef_loadtest >/dev/null 2>&1; then break; fi
  sleep 1
done

# 2) Backend de produção + Redis.
docker compose -f "$COMPOSE" up -d --build
echo "aguardando /health/ em 127.0.0.1:${LOADTEST_PORT}..."
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${LOADTEST_PORT}/health/" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${LOADTEST_PORT}/health/" >/dev/null || {
  echo "backend nao respondeu; veja: docker compose -f $COMPOSE logs backend"; exit 1; }

# 3) Semente.
docker compose -f "$COMPOSE" exec -T backend python manage.py seed_demo | tail -3
echo "alvo pronto: http://127.0.0.1:${LOADTEST_PORT}  (workers: ${GUNICORN_WORKERS:-4})"
