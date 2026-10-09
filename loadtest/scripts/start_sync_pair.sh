#!/usr/bin/env bash
# O PAR NUVEM + LOJA, na máquina local, para validar a sincronização de verdade.
#
#   bash loadtest/scripts/start_sync_pair.sh          # nuvem 8021, loja 8022
#   bash loadtest/scripts/start_sync_pair.sh --down   # derruba tudo
#
# A ORDEM IMPORTA, e é por isso que existe um script e não só um compose:
#
#   1. sobe os dois Postgres (bancos SEPARADOS — com um só, "chegou na loja"
#      seria a mesma linha que a nuvem acabou de gravar);
#   2. sobe a NUVEM e a semeia;
#   3. LÊ do banco da nuvem o UUID da conta — ele só existe depois da semente;
#   4. sobe a LOJA e o `sync_worker` com essa identidade, e a loja se matricula.
#
# Sem o passo 3 a loja sobe sem `SYNC_ACCOUNT_ID` e a matrícula para pedindo o
# dado no terminal — o sintoma que a doc de configuração descreve.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$RAIZ/docker/loadtest/docker-compose.pair.yml"
REDE="starchef-syncpair"
PG_NUVEM="starchef-pg-cloud"
PG_LOJA="starchef-pg-store"
SENHA_PG="sync-pair-only-password"

compose() { docker compose -f "$COMPOSE" -p syncpair "$@"; }

if [ "${1:-}" = "--down" ]; then
  compose down -v --remove-orphans || true
  docker rm -f "$PG_NUVEM" "$PG_LOJA" >/dev/null 2>&1 || true
  docker network rm "$REDE" >/dev/null 2>&1 || true
  echo "par de sincronizacao derrubado"
  exit 0
fi

export CLOUD_PORT="${CLOUD_PORT:-8021}"
export STORE_PORT="${STORE_PORT:-8022}"
export SYNC_ENROLL_USERNAME="${SYNC_ENROLL_USERNAME:-admin}"
export SYNC_ENROLL_PASSWORD="${SYNC_ENROLL_PASSWORD:-admin12345}"

docker network inspect "$REDE" >/dev/null 2>&1 || docker network create "$REDE" >/dev/null

# 1) Os dois bancos, zerados. Zerar é o ponto: a validação afirma "este registro
#    NÃO existia na loja e passou a existir", e num banco reaproveitado ela
#    passaria pelo resíduo da execução anterior.
subir_pg() {
  local nome="$1" banco="$2" porta="$3"
  docker rm -f "$nome" >/dev/null 2>&1 || true
  docker run -d --name "$nome" --network "$REDE" \
    -e POSTGRES_DB="$banco" -e POSTGRES_USER=starchef \
    -e POSTGRES_PASSWORD="$SENHA_PG" \
    --network-alias "${nome#starchef-}" \
    -p "127.0.0.1:${porta}:5432" postgres:16-alpine >/dev/null
  for _ in $(seq 1 40); do
    docker exec "$nome" pg_isready -U starchef -d "$banco" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "Postgres $nome nao respondeu" >&2
  return 1
}
subir_pg "$PG_NUVEM" starchef_cloud "${PG_CLOUD_PORT:-5434}"
subir_pg "$PG_LOJA"  starchef_store "${PG_STORE_PORT:-5435}"
echo "bancos no ar: nuvem 127.0.0.1:${PG_CLOUD_PORT:-5434}  loja 127.0.0.1:${PG_STORE_PORT:-5435}"

# A imagem é a mesma do alvo de carga: se ela não existe, constrói.
if ! docker image inspect starchef-backend:loadtest >/dev/null 2>&1; then
  echo "construindo starchef-backend:loadtest..."
  docker build -t starchef-backend:loadtest \
    --build-arg REQUIREMENTS=production \
    --build-arg "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST:-pypi.org files.pythonhosted.org}" \
    "$RAIZ/backend" >/dev/null
fi

# 2) A nuvem.
compose up -d redis-cloud redis-store backend-cloud
echo -n "aguardando a nuvem em 127.0.0.1:${CLOUD_PORT}"
for _ in $(seq 1 150); do
  if curl -fsS "http://127.0.0.1:${CLOUD_PORT}/health/" >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 2
done
curl -fsS "http://127.0.0.1:${CLOUD_PORT}/health/" >/dev/null || {
  echo; echo "a nuvem nao respondeu; veja: docker compose -f $COMPOSE -p syncpair logs backend-cloud"; exit 1; }

compose exec -T backend-cloud python manage.py seed_demo --skip-orders --skip-tenant-2 | tail -3

# O Celery da nuvem sobe DEPOIS da semente: a carga total que a matricula
# enfileira precisa de um worker na fila `sync.bootstrap` para sair, e o beat e
# quem avisa a loja de que ha fila esperando. Sem os dois, o par sobe inteiro,
# a loja se autentica e NADA sincroniza.
compose up -d celery_worker_cloud celery_beat_cloud

# 3) A identidade da conta. Vem do BANCO, e não de um id fixo no arquivo: o
#    `seed_demo` gera UUID novo a cada semente.
SYNC_ACCOUNT_ID="$(docker exec "$PG_NUVEM" psql -U starchef -d starchef_cloud -qtA \
  -c "SELECT id FROM accounts_account ORDER BY created_at LIMIT 1")"
export SYNC_ACCOUNT_ID
if [ -z "$SYNC_ACCOUNT_ID" ]; then
  echo "nao achei a conta no banco da nuvem — a semente falhou?" >&2
  exit 1
fi
echo "conta da nuvem: $SYNC_ACCOUNT_ID"

# 4) A loja, já com a identidade. `up` (e não `restart`) porque `environment` é
#    lido na CRIAÇÃO do container.
compose up -d backend-store sync_worker celery_worker_store celery_beat_store
echo -n "aguardando a loja em 127.0.0.1:${STORE_PORT}"
for _ in $(seq 1 150); do
  if curl -fsS "http://127.0.0.1:${STORE_PORT}/health/" >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 2
done

echo
echo "par pronto:"
echo "  NUVEM ..: http://127.0.0.1:${CLOUD_PORT}   (banco starchef_cloud)"
echo "  LOJA ...: http://127.0.0.1:${STORE_PORT}   (banco starchef_store)"
echo "  conta ..: $SYNC_ACCOUNT_ID"
echo
echo "acompanhe a matricula:"
echo "  docker compose -f $COMPOSE -p syncpair logs -f sync_worker"
echo
echo "valide a sincronizacao dos recursos novos:"
echo "  .venv/Scripts/python loadtest/validar_sync_par.py"
