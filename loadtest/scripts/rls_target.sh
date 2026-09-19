#!/usr/bin/env bash
# Liga Row Level Security no alvo de carga que já está no ar.
#
#   bash loadtest/scripts/rls_target.sh         # liga
#   bash loadtest/scripts/rls_target.sh --off   # desliga
#
# A pergunta que isto responde não é "o isolamento funciona" — disso cuidam os
# testes em `apps/core/tests/test_rls_postgres.py`. É a outra: **a aplicação
# inteira continua funcionando com a política de pé?** O modo de falhar do RLS
# é um endpoint qualquer que consultava fora do contexto de conta e passa a
# receber zero linha, sem erro nenhum. Só a carga sobre a API toda acha isso.
#
# Três passos, e o terceiro é o que quase todo mundo esquece:
#
#   1. cria um papel de aplicação SEM superusuário;
#   2. instala as políticas (como dono das tabelas);
#   3. faz o backend conectar COM esse papel.
#
# Sem o passo 3 a carga passaria inteira em verde sem ter exercitado nada:
# superusuário ignora toda política, e `FORCE ROW LEVEL SECURITY` não o
# alcança — ele só estende a política ao dono da tabela.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$RAIZ/docker/loadtest/docker-compose.yml"
OVERRIDE="$RAIZ/docker/loadtest/docker-compose.rls.yml"
PG="starchef-pg-loadtest"
DONO="starchef"
APP="starchef_app"
BANCO="starchef_loadtest"

psql_dono() { docker exec -i "$PG" psql -U "$DONO" -d "$BANCO" -v ON_ERROR_STOP=1 -q "$@"; }

if [ "${1:-}" = "--off" ]; then
  # A ORDEM importa, e errá-la custou uma execução: remover política exige ser
  # DONO das tabelas (`must be owner of relation accounts_account`), e o
  # backend ainda está conectando como o papel de aplicação, que não é dono.
  # Primeiro devolve a conexão ao dono, DEPOIS remove.
  docker compose -f "$COMPOSE" up -d --no-deps backend
  for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:${LOADTEST_PORT:-8012}/health/" >/dev/null 2>&1; then break; fi
    sleep 2
  done
  docker compose -f "$COMPOSE" exec -T backend python manage.py install_rls --remove | tail -2
  echo "RLS desligada; backend voltou a conectar como $DONO"
  exit 0
fi

echo "1/3 papel de aplicação sem superusuário…"
psql_dono <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$APP') THEN
    CREATE ROLE $APP LOGIN PASSWORD 'loadtest-only-password' NOSUPERUSER NOBYPASSRLS;
  END IF;
END \$\$;
GRANT CONNECT ON DATABASE $BANCO TO $APP;
GRANT USAGE ON SCHEMA public TO $APP;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $APP;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $APP;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $APP;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO $APP;
SQL

echo "2/3 instalando as políticas…"
docker compose -f "$COMPOSE" exec -T backend python manage.py install_rls | tail -3

echo "3/3 backend passa a conectar como $APP, com RLS_ENABLED=true…"
docker compose -f "$COMPOSE" -f "$OVERRIDE" up -d --no-deps backend
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${LOADTEST_PORT:-8012}/health/" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${LOADTEST_PORT:-8012}/health/" >/dev/null || {
  echo "backend não voltou; veja: docker compose -f $COMPOSE logs backend"; exit 1; }

docker compose -f "$COMPOSE" -f "$OVERRIDE" exec -T backend python manage.py install_rls --status | head -8
echo "alvo com RLS LIGADA. Rode a carga e compare com a execução sem RLS."
