#!/bin/sh
set -e

# Reimplementa o que o envsubst automático do nginx fazia: injeta a URL da
# API em window.RUNTIME_CONFIG antes do `serve` subir. WS_URL é opcional —
# vazio faz o frontend derivar o WebSocket da própria API_URL.
sed -e "s|\${API_URL}|$API_URL|g" \
    -e "s|\${WS_URL}|$WS_URL|g" \
    runtime-config.js.template > dist/runtime-config.js

exec "$@"
