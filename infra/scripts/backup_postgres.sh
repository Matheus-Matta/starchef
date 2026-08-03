#!/bin/sh
# Backup diário do Postgres de produção + limpeza de backups antigos.
# Roda em loop dentro do serviço `postgres_backup` do docker-compose.prod.yml
# (mesma imagem postgres:16-alpine já usada pelo banco — sem dependência nova).
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"

mkdir -p "$BACKUP_DIR"

while true; do
  stamp=$(date -u +%Y%m%d_%H%M%S)
  target="$BACKUP_DIR/starchef_${stamp}.sql.gz"
  echo "[backup] iniciando dump para $target"

  if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
      -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      | gzip > "$target"; then
    echo "[backup] concluído: $target"
  else
    echo "[backup] FALHOU ao gerar $target" >&2
    rm -f "$target"
  fi

  find "$BACKUP_DIR" -name 'starchef_*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
  echo "[backup] próximo dump em ${INTERVAL_SECONDS}s"
  sleep "$INTERVAL_SECONDS"
done
