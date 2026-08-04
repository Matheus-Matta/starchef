# Build de produção do frontend (Vue + Vite). Multi-stage: compila o SPA no
# Node e entrega os estáticos por um servidor estático simples (`serve`) — sem
# nginx. TLS e o proxy same-origin de /api e /ws são responsabilidade de um
# proxy reverso EXTERNO a este compose (nginx do host, Caddy, LB da nuvem
# etc.); esta imagem só serve os arquivos do build em HTTP puro.

# ── Stage 1: build ───────────────────────────────────────────────────────────
# jsdom 30/vitest 4 exigem Node >=22 (mesma razão do bump em .github/workflows/frontend.yml).
FROM node:24-alpine AS build
WORKDIR /app

# Instala deps a partir do lockfile (build reproduzível).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# URL da API no bundle. Same-origin por padrão (/api/v1): o proxy externo deve
# servir o SPA e fazer proxy do /api na mesma origem — sem CORS e compatível
# com cookies SameSite=Lax.
RUN npm run build

# ── Stage 2: runtime (serve) ─────────────────────────────────────────────────
FROM node:24-alpine
WORKDIR /app

# Pin de versão pelo mesmo motivo do `npm ci` no stage 1: build reproduzível.
RUN npm install -g serve@14.2.6

COPY --from=build /app/dist ./dist
COPY runtime-config.js.template ./runtime-config.js.template
COPY serve.json ./dist/serve.json
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

ENV API_URL=/api/v1
EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["serve", "-s", "dist", "-l", "8080"]
