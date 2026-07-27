# Build de produção do frontend (Vue + Vite) servido por nginx.
# Multi-stage: compila o SPA no Node e entrega só os estáticos no nginx (imagem enxuta).
# Esta imagem é a BORDA de produção: serve o SPA e faz proxy de /api e /ws para o
# backend (config em infra/nginx.prod.conf, montada em runtime).

# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

# Instala deps a partir do lockfile (build reproduzível).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# URL da API no bundle. Same-origin por padrão (/api/v1): o nginx serve o SPA e
# faz proxy do /api na mesma origem — sem CORS e compatível com cookies SameSite=Lax.
RUN npm run build

# ── Stage 2: runtime (nginx) ─────────────────────────────────────────────────
FROM nginx:1.27-alpine
# Apenas os estáticos compilados; a config do nginx é montada pelo compose.
COPY --from=build /app/dist /usr/share/nginx/html
COPY runtime-config.js.template /etc/nginx/templates/runtime-config.js.template
ENV API_URL=/api/v1
ENV NGINX_ENVSUBST_OUTPUT_DIR=/usr/share/nginx/html
EXPOSE 80 443
