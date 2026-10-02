#!/usr/bin/env sh
# Gera um ambiente local de produção sem depender de arquivos .env de exemplo.
# Rode nesta pasta com: sh instalar.sh
set -eu
cd "$(dirname "$0")"
umask 077
ENV_FILE=.env.local
compose() { docker compose --env-file "$ENV_FILE" -f docker-compose.local.yml "$@"; }
segredo() { od -An -v -N "$1" -tx1 /dev/urandom | tr -d ' \n'; }
ler() { sed -n "s/^[[:space:]]*$1=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'; }
gravar() {
  temporario="$ENV_FILE.tmp.$$"
  ENV_KEY=$1 ENV_VALUE=$2 awk '
    BEGIN { key = ENVIRON["ENV_KEY"]; found = 0 }
    $0 ~ "^[[:space:]]*" key "=" {
      print key "=" ENVIRON["ENV_VALUE"]; found = 1; next
    }
    { print }
    END { if (!found) print key "=" ENVIRON["ENV_VALUE"] }
  ' "$ENV_FILE" > "$temporario"
  chmod 600 "$temporario"
  mv "$temporario" "$ENV_FILE"
}
default() { [ -n "$(ler "$1")" ] || gravar "$1" "$2"; }
segredo_se_faltar() { [ -n "$(ler "$1")" ] || gravar "$1" "$(segredo "$2")"; }
ip_da_loja() {
  hostname -I 2>/dev/null | tr ' ' '\n' |
    grep -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' | head -n 1
}
mostrar_chaves() {
  echo
  echo "Guarde estas chaves em local seguro:"
  for chave in POSTGRES_USER POSTGRES_DB POSTGRES_PASSWORD DJANGO_SECRET_KEY \
    DJANGO_FIRST_ACCESS_TOKEN SYNC_METRICS_TOKEN; do
    printf '  %s=%s\n' "$chave" "$(ler "$chave")"
  done
  echo
}
if [ ! -f "$ENV_FILE" ]; then
  : > "$ENV_FILE"
  echo "Criado $ENV_FILE com configurações de produção."
fi
chmod 600 "$ENV_FILE"
for chave in POSTGRES_DB:starchef_local POSTGRES_USER:starchef \
  DJANGO_ENV:production DJANGO_SETTINGS_MODULE:config.settings.production \
  DJANGO_DEBUG:false USE_SQLITE_DATABASE:false USE_LOCAL_MEMORY_SERVICES:false \
  POSTGRES_HOST:postgres POSTGRES_PORT:5432 \
  REDIS_URL:redis://redis:6379/0 CELERY_BROKER_URL:redis://redis:6379/1 \
  CELERY_RESULT_BACKEND:redis://redis:6379/2 \
  DJANGO_SECURE_SSL_REDIRECT:false DJANGO_SESSION_COOKIE_SECURE:false \
  DJANGO_CSRF_COOKIE_SECURE:false DJANGO_AUTH_COOKIE_SECURE:false \
  SYNC_ENVIRONMENT:production \
  SYNC_AUTO_ENROLL:true SYNC_NODE_TYPE:local \
  SYNC_ENROLL_ENV_PATH:/app/sync/credentials.env SYNC_STALE_NEVER_SEEN_DAYS:7 \
  SYNC_STALE_SILENT_DAYS:30 FISCAL_TRANSMIT_VIA_CLOUD:true FISCAL_RELAY_TIMEOUT:45 \
  HTTP_PORT:80 HTTP_BIND:0.0.0.0 BACKEND_PORT:8000 BACKEND_BIND:0.0.0.0 \
  GUNICORN_WORKERS:3 CELERY_CONCURRENCY:2 POSTGRES_POOL:true \
  POSTGRES_POOL_MIN:2 POSTGRES_POOL_MAX:8 SYNC_BATCH_MAX_EVENTS:200 \
  SYNC_BATCH_MAX_BYTES:1048576 SYNC_RETENTION_DAYS:30 SYNC_INTERVAL:2 \
  SYNC_HEARTBEAT:20 SYNC_FILE_MAX_BYTES:67108864 \
  SENTRY_ENVIRONMENT:production SENTRY_TRACES_SAMPLE_RATE:0.1 SENTRY_SEND_PII:false \
  POSTGRES_CELERY_CONN_MAX_AGE:60 POSTGRES_CONN_MAX_AGE:60 \
  DJANGO_EMAIL_HOST:localhost DJANGO_EMAIL_PORT:587 DJANGO_EMAIL_USE_TLS:true \
  DJANGO_EMAIL_USE_SSL:false PASSWORD_RESET_TIMEOUT_MINUTES:30 \
  FOCUS_NFE_PRODUCTION_URL:https://api.focusnfe.com.br \
  FOCUS_NFE_HOMOLOGATION_URL:https://homologacao.focusnfe.com.br \
  FOCUS_NFE_TIMEOUT_SECONDS:30 FOCUS_NFE_AUTO_SYNC:true FOCUS_NFE_COMPANY_DRY_RUN:false \
  IMAGE_UPLOAD_MAX_BYTES:8388608 RLS_ENABLED:false \
  POSTGRES_MEM_LIMIT:1g REDIS_MEM_LIMIT:256m REDIS_MAXMEMORY:192mb \
  BACKEND_MEM_LIMIT:1g CELERY_WORKER_MEM_LIMIT:768m CELERY_BEAT_MEM_LIMIT:256m \
  SYNC_WORKER_MEM_LIMIT:512m FRONTEND_MEM_LIMIT:256m PROXY_MEM_LIMIT:128m; do
  chave_nome=${chave%%:*}
  chave_valor=${chave#*:}
  default "$chave_nome" "$chave_valor"
done
gravar SYNC_ENABLED true
for chave in STORE_HOST DJANGO_ALLOWED_HOSTS DJANGO_CORS_ALLOWED_ORIGINS \
  DJANGO_CSRF_TRUSTED_ORIGINS SYNC_ACCOUNT_ID SYNC_STORE_ID SYNC_ENROLL_USERNAME \
  SYNC_ENROLL_PASSWORD SYNC_NODE_ID SYNC_PAIR_ID SYNC_PEER_NODE_ID SYNC_AUTH_TOKEN \
  SYNC_CLOUD_API_URL SYNC_CLOUD_WSS_URL SYNC_ENROLL_SECRET SYNC_NODE_NAME \
  SYNC_ENCRYPTION_KEY SYNC_ENCRYPTION_KEY_ID AWS_STORAGE_BUCKET_NAME \
  AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_S3_REGION_NAME AWS_S3_ENDPOINT_URL \
  SENTRY_DSN; do
  default "$chave" ""
done
default DJANGO_EMAIL_BACKEND django.core.mail.backends.smtp.EmailBackend
default DJANGO_EMAIL_HOST_USER ""
default DJANGO_EMAIL_HOST_PASSWORD ""
default DJANGO_EMAIL_HOST localhost
default DJANGO_EMAIL_PORT 587
default DJANGO_EMAIL_USE_TLS true
default DJANGO_EMAIL_USE_SSL false
default DJANGO_DEFAULT_FROM_EMAIL 'StarChef <no-reply@localhost>'
default DJANGO_AUTH_COOKIE_SAMESITE Lax
default DJANGO_AUTH_COOKIE_DOMAIN ""
default DJANGO_JWT_AUTH_COOKIE sc_access
default DJANGO_JWT_AUTH_REFRESH_COOKIE sc_refresh
default DJANGO_STOREFRONT_JWT_AUTH_COOKIE sf_access
default DJANGO_STOREFRONT_JWT_REFRESH_COOKIE sf_refresh
default PASSWORD_RESET_TIMEOUT_MINUTES 30
default RLS_ENABLED false
default POSTGRES_POOL_TIMEOUT 10
default POSTGRES_CONN_HEALTH_CHECKS false
default POSTGRES_CELERY_CONN_MAX_AGE 60
default POSTGRES_CONN_MAX_AGE 60
default FOCUS_NFE_MASTER_TOKEN ""
default FOCUS_NFE_WEBHOOK_URL ""
default FOCUS_NFE_WEBHOOK_AUTHORIZATION ""
default FOCUS_NFE_WEBHOOK_AUTHORIZATION_HEADER Authorization
default FOCUS_NFE_PRODUCTION_URL https://api.focusnfe.com.br
default FOCUS_NFE_HOMOLOGATION_URL https://homologacao.focusnfe.com.br
default FOCUS_NFE_TIMEOUT_SECONDS 30
default FOCUS_NFE_AUTO_SYNC true
default FOCUS_NFE_COMPANY_DRY_RUN false
default FISCAL_TRANSMIT_VIA_CLOUD true
default FISCAL_RELAY_TIMEOUT 45
default IMAGE_UPLOAD_MAX_BYTES 8388608
default AWS_S3_REGION_NAME auto
default AWS_S3_CUSTOM_DOMAIN ""
default AWS_QUERYSTRING_AUTH false
segredo_se_faltar POSTGRES_PASSWORD 32
segredo_se_faltar DJANGO_SECRET_KEY 48
segredo_se_faltar DJANGO_FIRST_ACCESS_TOKEN 24
segredo_se_faltar SYNC_METRICS_TOKEN 32
if [ -z "$(ler STARCHEF_VERSION)" ]; then
  printf 'Versão da imagem StarChef [latest]: '
  read -r versao || versao=""
  gravar STARCHEF_VERSION "${versao:-latest}"
fi
atual=$(ler STORE_HOST)
if [ -z "$atual" ] || [ "$atual" = "192.168.0.10" ]; then
  sugerido=$(ip_da_loja || true)
  printf 'IP/nome deste servidor na rede da loja [%s]: ' "$sugerido"
  read -r resposta || resposta=""
  resposta=${resposta:-$sugerido}
  if [ -z "$resposta" ]; then
    echo "Informe o IP/nome do servidor em STORE_HOST e rode novamente." >&2
    exit 1
  fi
  gravar STORE_HOST "$resposta"
fi

host=$(ler STORE_HOST)
porta=$(ler HTTP_PORT)
origens="http://$host,http://$host:$porta,http://localhost,http://localhost:$porta"
gravar DJANGO_ALLOWED_HOSTS "localhost,127.0.0.1,backend,proxy,$host"
gravar DJANGO_CORS_ALLOWED_ORIGINS "$origens"
gravar DJANGO_CSRF_TRUSTED_ORIGINS "$origens"
default FRONTEND_URL "http://$host"

. ./configurar-sincronizacao.sh

mostrar_chaves
if ! docker info >/dev/null 2>&1; then
  echo "O .env.local foi criado, mas o Docker não está rodando. Abra o Docker e rode novamente." >&2
  exit 1
fi
compose config --quiet
compose pull
compose up -d

porta=$(ler HTTP_PORT)
base="http://$(ler STORE_HOST)"
[ "$porta" = 80 ] || base="$base:$porta"
echo "Esperando o backend ficar pronto (a primeira subida pode levar alguns minutos)..."
tentativa=0
while [ "$tentativa" -lt 60 ]; do
  if curl -fsS "http://127.0.0.1:$porta/health/" >/dev/null 2>&1; then
    echo "StarChef no ar: $base/ (API $base/api/v1, Admin $base/admin/)"
    echo "Token do primeiro acesso: $(ler DJANGO_FIRST_ACCESS_TOKEN)"
    echo "Sincronização: $(ler SYNC_NODE_NAME) ($(ler SYNC_ACCOUNT_ID))"
    exit 0
  fi
  tentativa=$((tentativa + 1))
  sleep 10
done
echo "O backend não respondeu em 10 minutos. Consulte os logs do serviço backend." >&2
exit 1
