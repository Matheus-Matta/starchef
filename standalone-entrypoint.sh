#!/bin/bash
set -e

# Inicia o Postgres e Redis temporariamente para migrations
service postgresql start
service redis-server start
sudo -u postgres psql -c "CREATE USER starchef WITH PASSWORD 'standalone-postgres-secure-password';" || true
sudo -u postgres psql -c "CREATE DATABASE starchef OWNER starchef;" || true

echo "Rodando migrations..."
# Garante as perms da midia antes
chown -R appuser:appuser /app/backend/media /app/backend/staticfiles || true
sudo -E -u appuser bash -c "source /app/.venv/bin/activate && cd /app/backend && python manage.py migrate --noinput"
sudo -E -u appuser bash -c "source /app/.venv/bin/activate && cd /app/backend && python manage.py collectstatic --noinput"

echo "Populando banco com dados de teste..."
sudo -E -u appuser bash -c "source /app/.venv/bin/activate && cd /app/backend && python manage.py seed_demo" || true

# Para o postgres e redis (o supervisor vai subir de novo de forma persistente)
service postgresql stop
service redis-server stop

echo "Iniciando supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
