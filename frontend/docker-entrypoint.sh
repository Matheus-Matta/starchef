#!/bin/sh
set -e

# Reimplementa o que o envsubst automático do nginx fazia: injeta a URL da
# API em window.RUNTIME_CONFIG antes do `serve` subir.
sed "s|\${API_URL}|$API_URL|g" runtime-config.js.template > dist/runtime-config.js

exec "$@"
