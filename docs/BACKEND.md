# StarChef Backend — Guia Completo

> Django REST API multi-tenant para gestão de restaurantes: pedidos, PDV, KDS, caixa, cardápio, estoque, impressão/balanças e relatórios. Este documento cobre visão geral, arquitetura, como rodar em desenvolvimento e como funciona em produção. Para o inventário de features de negócio faltando, veja [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md); para a arquitetura de código/estrutura em nível macro, veja [`ARCHITECTURE.md`](ARCHITECTURE.md) (mais enxuto, complementar a este).

## 1. Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Framework | Django 5 + Django REST Framework |
| Tempo real | Django Channels + Redis (WebSocket) |
| Fila/agendamento | Celery + Redis (broker/result backend) |
| Auth | `djangorestframework-simplejwt`, JWT em cookies httpOnly |
| Banco | PostgreSQL (produção) / SQLite (dev e testes) |
| Documentação de API | `drf-spectacular` (OpenAPI/Swagger) |
| Admin | `django-unfold` (UI customizada sobre o Django Admin) |
| Config/env | `python-decouple` |
| Servidor ASGI | Daphne (dev) / Gunicorn + `uvicorn.workers.UvicornWorker` (produção) |
| Erros/observabilidade | Sentry (opcional, via `SENTRY_DSN`) |
| Lint | `ruff` |
| Testes | `pytest` + `pytest-django` + `pytest-cov` |

## 2. Estrutura de pastas

```
backend/
  config/                 settings (base/development/production/test), urls.py, routing.py (WS), celery.py, asgi.py
  apps/
    core/                 infraestrutura transversal (ver §4)
    accounts/             conta (tenant raiz), planos, usuários, perfis, papéis/permissões, login
    restaurants/          Restaurant/Branch, mesas, setores, comandas, zonas/entregadores de delivery
    customers/             clientes e endereços
    menu/                  categorias, produtos, variações, adicionais, ingredientes, receitas, cardápios (Menu/MenuItem)
    orders/                pedidos, itens, lotes de produção, WebSocket de cozinha (KitchenConsumer)
    kitchen/               telas/config do KDS (estações e colunas)
    payments/              formas de pagamento, pagamentos, caixa (CashRegister/CashMovement)
    printers/              impressoras, balanças, leituras de peso, fila de impressão (PrintJob)
    stock/                 locais de estoque e movimentações
    invoices/               perfil/config fiscal, notas e provedores Manual + Focus NFe
    integrations/           contratos de integração externa (ex.: FiscalProvider)
    reports/                endpoints de relatórios agregados
    sla/                    acordos de nível de serviço operacionais
    notifications/          notificações internas + WebSocket
    realtime/               canal WebSocket genérico por conta (broadcast de eventos de modelo)
    data_exchange/          import/export CSV
  requirements/            base.txt / development.txt / production.txt
  tests/                   testes de integração cross-app (fluxo de pedido, auth, balança, impressão de comanda)
  gunicorn.conf.py         config do Gunicorn em produção
  pyproject.toml           config do ruff
  pytest.ini
```

Cada app de domínio segue o padrão: `models.py`, `serializers.py`, `views.py` (ViewSets DRF), `admin.py`, e `services.py` quando há regra transacional não trivial (ex.: `orders/services.py`, `payments/services.py`, `printers/services.py`).

As credenciais da Focus NFe ficam em `accounts.FocusNfeConfig`, numa relação `OneToOne` com `Account`. O `.env` apenas provisiona esse registro na migration/criação da conta; chamadas externas nunca usam o `.env` como fallback.

As credenciais da Bluesoft Cosmos ficam em `accounts.CosmosConfig`, também em
`OneToOne` com `Account`. A integração nasce desativada e não usa fallback do
`.env`: cada conta informa seu próprio `X-Cosmos-Token` e `User-Agent`. O token
é somente escrita; a API devolve apenas `api_token_configured`/`is_ready`.
`apps/invoices/cosmos.py` pesquisa produtos por descrição, sugere NCM/CEST e
mantém o resultado em cache por sete dias para economizar a cota da Cosmos.

## 3. Como rodar em desenvolvimento

Pré-requisito: um venv Python com `pip install -r backend/requirements/development.txt`. Por padrão, dev usa **SQLite** e serviços locais em memória (sem precisar de Postgres/Redis rodando).

A partir da raiz do monorepo (`package.json` raiz tem os atalhos):

```bash
npm run dev            # sobe backend (Daphne) + frontend (Vite) + Celery worker/beat juntos, um Ctrl+C encerra tudo
npm run dev:backend    # só o backend: manage.py runserver 0.0.0.0:8001 --noreload
npm run migrate        # manage.py migrate
npm run seed           # manage.py seed_demo — popula dados de demonstração
npm run shell          # manage.py shell
```

`npm run dev` usa o comando customizado `manage.py runservices`, que orquestra tudo num terminal só (libera a porta antes de subir, roda migrations com `--migrate`, pula Celery worker/beat se `CELERY_TASK_ALWAYS_EAGER=True`, que é o padrão em dev).

Comandos de management úteis (`apps/*/management/commands/`):

| Comando | O que faz |
|---|---|
| `seed_demo [--reset-sqlite]` | Popula/reseta dados de demonstração (conta, filial, papéis, usuário, produtos) |
| `sync_permissions` | Upsert idempotente do catálogo canônico de permissões a partir de `apps/accounts/permission_catalog.py` |
| `create_tenant_user` | Cria/atualiza um usuário com perfil de tenant corretamente configurado (account/restaurant/branch/role) |
| `runservices` | Orquestra backend+frontend+Celery localmente |

Rodar os testes:

```bash
cd backend
python -m pytest -q                                    # suíte completa
python -m pytest --cov=apps --cov-report=term-missing   # com cobertura
python -m pytest apps/<app> -q                          # só um app
ruff check .                                             # lint
manage.py makemigrations --check --dry-run               # checar migration pendente
```

## 4. `apps/core` — infraestrutura transversal

Todo modelo de domínio herda de classes base em `apps/core/models.py`:

- `UUIDModel` — PK `UUID`.
- `TimeStampedModel` — `created_at`/`updated_at`.
- `SoftDeleteModel` — soft delete (`deleted_at`); o manager padrão filtra deletados, `all_objects` acessa tudo.
- `TenantModel` — combina UUID + timestamps + auditoria + escopo automático por conta (a base usada pela maioria dos modelos de domínio).
- `AuditLog` — log de auditoria genérico (usado por `apps/core/audit.py:record_audit`).
- `IdempotencyRecord` — suporte ao middleware de idempotência (abaixo).

Outras peças centrais:

- **`apps/core/idempotency.py`** — `IdempotencyMiddleware`, registrado globalmente no `MIDDLEWARE`. Aplica-se a **todo** `POST/PUT/PATCH/DELETE` da API (exceto `/api/v1/auth/` e `/admin/`) que enviar o header `Idempotency-Key`: a primeira execução grava a resposta junto da chave; repetições devolvem a resposta gravada sem reexecutar nada. Existe justamente para o PDV Flutter poder reenviar operações da fila offline sem duplicar venda.
- **`apps/core/permissions.py`** — `HasTenantAccess` (usuário precisa pertencer a um tenant) e `HasModulePermission` (bloqueia endpoints de módulos opcionais não contratados pela conta — ver módulos abaixo).
- **`apps/core/modules.py`** — sistema de módulos: `MODULE_BASE` (sempre liberado) + opcionais `financeiro`, `logistica`, `ecommerce`, `entrega`, habilitados por conta em `Account.enabled_modules` (JSON field). Views declaram `required_module = MODULE_FINANCEIRO` (por exemplo `invoices` e `stock`); sem o módulo, a API responde 403.
- **`apps/core/admin_mixins.py`** — `TenantAdminMixin`/`TenantModelAdmin` (base do Unfold) filtram automaticamente queryset e FKs por tenant no admin, preenchem `account` ao salvar e ignoram soft-deleted.
- **`apps/core/tenant.py`** — `ContextVar` que expõe a conta corrente fora do ciclo request/response (ex.: dentro de tasks Celery, via `celery_tenant_context`).

## 5. Autenticação e multi-tenancy

- **Login** (`LoginView`, baseado em `TokenObtainPairView`): valida credenciais, retorna os tokens no corpo **e** grava em cookies httpOnly (`apps/core/cookies.py:set_auth_cookies`) — a menos que a requisição peça `no_cookie=true` (usado na reautenticação gerencial temporária do caixa, ver `CashRegisterView` no frontend). Também grava `sc_session`, um cookie legível (sem valor sensível) só para o frontend saber que há sessão sem precisar decodificar o JWT.
- **Refresh**: `CookieTokenRefreshView` lê o refresh token do corpo ou do cookie, reemite tokens e regrava os cookies.
- **Logout**: `LogoutView` faz blacklist do refresh token e limpa os cookies.
- **Autenticação por requisição**: `apps/core/authentication.py:CookieJWTAuthentication` tenta primeiro `Authorization: Bearer`, senão cai no cookie httpOnly. Proteção CSRF vem do `SameSite=Lax` (cookie não trafega em POST/PUT/PATCH/DELETE cross-site).
- **Resolução de tenant**: `apps/core/middleware.py:TenantMiddleware` roda em toda request (exceto rotas públicas) e autentica o JWT manualmente antes do DRF. Resolve `request.account` a partir de `user.profile.account`; o superusuário pode injetar `X-Account-ID` no header para escolher outro tenant. **A API nunca opera em escopo global** — nem para superusuário, que age como admin da conta a que está vinculado. Sem conta resolvida a request é barrada (403 com mensagem explícita) e o login nem completa; os querysets tenant ainda devolvem vazio como segunda camada (`TenantQuerySetMixin`). Enxergar todas as contas de uma vez é papel do `/admin`, que é isento deste middleware. A identidade também vem sempre do JWT, nunca do `sessionid`: estar logado no `/admin` no mesmo navegador não muda o que a API entrega ao app (e o cookie de sessão fica restrito a `/admin/` via `SESSION_COOKIE_PATH`). Há uma segunda camada, `TenantResponseSafetyMiddleware`, que varre o JSON de resposta e bloqueia qualquer registro cujo `account_id` não bata com o tenant da requisição — defesa em profundidade contra vazamento cross-tenant.

## 6. WebSocket / tempo real

`config/routing.py` agrega as rotas WebSocket autenticadas via `apps/core/jwt_middleware.py:JwtAuthMiddlewareStack`. A credencial é lida primeiro de `Authorization: Bearer <access JWT>`, depois do cookie httpOnly e, apenas para clientes antigos, de `?token=`. O Caixa Principal usa o header Bearer para que o token não apareça em URLs nem em logs de proxy.

| Rota | Consumer | Uso |
|---|---|---|
| `/ws/realtime/` | `apps/realtime/consumers.py:RealtimeConsumer` | Canal genérico por conta; qualquer app pode publicar eventos de modelo via `broadcast_model_event` (`apps/realtime/events.py`) para o frontend atualizar listas/boards sem polling |
| `/ws/pdv/<restaurant_id>/` | `apps/realtime/consumers.py:PdvRealtimeConsumer` | Canal dedicado do Caixa Principal. Exige JWT válido, confirma que o restaurante está ativo e pertence à conta do usuário e descarta eventos de outras unidades. Envia mudanças de mesas, comandas, pedidos/itens, produtos, clientes, pagamentos, caixa, impressoras, balanças e demais modelos do tenant |
| `/ws/kitchen/<branch_id>/<sector>/` | `apps/orders/consumers.py:KitchenConsumer` | Específico do KDS. Grupo por conta+filial+setor; acesso restrito a quem pertence à filial ou tem perfil admin/owner/manager. Eventos: `order_item.sent` (item mandado à cozinha) e `order_item.status_changed` |
| `/ws/notifications/...` | `apps/notifications/consumers.py:NotificationConsumer` | Grupo por usuário; envia contagem de não lidas na conexão e um evento `notification` por notificação nova |

O protocolo do PDV usa mensagens `{"event":"model.created|model.updated|model.deleted","payload":{...}}`. O payload contém somente metadados de invalidação (`resource`, `id`, `restaurant_id`, `branch_id`, `changed_fields`, `occurred_at` e `protocol_version`), nunca senhas ou dados completos. Ao receber o evento, o desktop relê pela API REST autenticada apenas o conjunto afetado e atualiza seu cache. A conexão mantém heartbeat, reconecta com backoff e faz uma única reconciliação ao reconectar; não há polling periódico de dados.

Os signals de `apps/realtime/signals.py` cobrem criação, alteração, exclusão lógica/física e relações N:N de todos os `TenantBaseModel`. Operações em lote de mesas/comandas, que não executam signals do Django, publicam um evento compacto de coleção explicitamente.

## 7. Pedidos, pagamento e impressão

**Ciclo de vida do `Order`** (`apps/orders/models.py`) tem três eixos independentes:

- `status`: `open → awaiting_payment → paid` (ou `cancelled`/`refunded`).
- `production_status`: `idle → sent_to_kitchen → preparing → partially_ready → ready → delivered`.
- `payment_status`: `pending → partial → paid` (ou `refunded`).

Regras aplicadas em `apps/orders/services.py`: pedido pago/cancelado/estornado fica bloqueado para alteração; cancelamento exige motivo; retroceder um item pronto exige perfil de gerente/dono/admin; mesa ocupada não abre pedido paralelo; fechamento e pagamento usam `transaction.atomic`; pagamento aceita `Idempotency-Key`.

**Senha de ações do caixa**: o cadastro de restaurante recebe a senha comum
escolhida pelo responsável (por exemplo, `123`), nunca uma hash. O modelo
converte automaticamente qualquer valor novo para PBKDF2-SHA256, inclusive
quando vem do Django Admin, import ou script; a API expõe apenas
`has_cash_action_password` e o endpoint autenticado `cash-auth` entrega a hash
ao PDV para verificação offline. A migration `restaurants.0003` converte valores
simples já existentes sem alterar hashes válidas.

**Impressão** (`apps/printers/services.py`): o backend **não** gera ESC/POS. `register_print_job` renderiza um template HTML (`apps/printers/templates/printers/{receipt,weigh_ticket}.html` etc. conforme o tipo) e grava em `PrintJob.html_content`, mais um payload de texto monoespaçado 48 colunas com código de barras Code128. Quem entrega fisicamente é o **agente local do desktop Flutter** (`local_device_agent.dart`, ver [`FLUTTER_DESKTOP.md`](FLUTTER_DESKTOP.md)). O agente recebe a criação do `PrintJob` pelo WebSocket do PDV, busca a fila pendente pela API e imprime via rede/serial/spool do SO; também reconcilia a fila uma vez ao conectar ou reconectar, sem polling periódico.

**Balanças**: `Scale` representa a balança física (porta, protocolo Toledo/Filizola/Urano/genérico), com `agent_instance_id` + `agent_lease_expires_at` — um lease de posse exclusiva por um agente desktop, para dois terminais não disputarem a mesma balança. `ScaleReading` é o peso reportado (pelo agente ou digitado manualmente no PDV), e quando vinculado a um `order_item` alimenta a precificação por quilo.

## 8. Celery

Configurado (`config/celery.py`), com Redis como broker/result backend em produção e `CELERY_TASK_ALWAYS_EAGER=True` em dev/test (roda síncrono, sem precisar de worker nem Redis). **Nenhuma task assíncrona está definida hoje** além do helper de contexto `celery_tenant_context` em `apps/core/tasks.py` — a infraestrutura (worker + beat, subidos pelo `runservices` e pelo `docker-compose.yml`) está pronta e conectada, mas não há jobs de fato agendados/enfileirados ainda.

## 9. Superfície da API

Tudo sob `/api/v1/...` (sem outra versão hoje). Pontos notáveis:

- `GET /api/v1/public/menu/<slug>/` — único endpoint sem autenticação (cardápio digital público).
- `GET /health/` — healthcheck (usado pelo Docker healthcheck e pelo proxy reverso externo).
- `GET /` — índice JSON com links (health/swagger/login).
- `GET /api/schema/` e `/api/schema/swagger-ui/` — OpenAPI via `drf-spectacular`.
- `/admin/` — Django Admin (Unfold), com `/admin/login/` cobrindo o fluxo de primeiro acesso.
- Todo o resto é `router.urls` (DRF `DefaultRouter`) — um ViewSet por recurso, RESTful padrão (list/retrieve/create/update/partial_update/destroy) mais actions customizadas onde necessário (ex.: `orders/send-to-kitchen`, `cash-register/open`, `cash-register/close`).
- `GET/PATCH /api/v1/integrations/cosmos/config/` configura a Cosmos da conta (somente administrador); `GET /api/v1/fiscal/profiles/cosmos-status/` e `cosmos-suggest/?query=...` sustentam o preenchimento assistido dos perfis fiscais sem gravar automaticamente.

## 10. Configuração / variáveis de ambiente

Documentadas na íntegra em `.env.example` (produção — é o que `docker-compose.yml` lê via `.env`), na raiz do monorepo. Os grupos principais:

- **Django core**: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_FIRST_ACCESS_TOKEN`.
- **Cookies/TLS**: `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_AUTH_COOKIE_SECURE`, `DJANGO_AUTH_COOKIE_SAMESITE`, `DJANGO_AUTH_COOKIE_DOMAIN`.
- **Banco**: `USE_SQLITE_DATABASE`, `POSTGRES_DB/USER/PASSWORD/HOST/PORT`, `POSTGRES_CONN_MAX_AGE`.
- **Redis/Celery**: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_CONCURRENCY`.
- **Gunicorn** (opcional): `GUNICORN_WORKERS/TIMEOUT/MAX_REQUESTS/LOG_LEVEL`.
- **Throttling DRF** (opcional, tem defaults sensatos): `THROTTLE_RATE_{ANON,USER,LOGIN,TOKEN_REFRESH,PASSWORD_RESET,DEVICE_POLL,CASH_APPROVAL,PUBLIC_MENU}`.
- **Sentry** (opcional): `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_SEND_PII`. Sem `SENTRY_DSN` em produção, o boot grava um `logger.warning` avisando que não há error tracking ativo (não falha o boot).
- **E-mail transacional**: `DJANGO_EMAIL_*`, `DEFAULT_FROM_EMAIL`, `PASSWORD_RESET_TIMEOUT_MINUTES`.

`SECRET_KEY` fraca ou `POSTGRES_PASSWORD` com valor default fazem o boot de produção falhar com `ImproperlyConfigured` (`config/settings/production.py`) — não tem como subir produção com esses defaults por engano.

## 11. Produção

### O que roda (`docker-compose.yml`)

```
postgres          — Postgres 16, sem porta exposta ao host, healthcheck
redis             — cache + Channels layer + broker/result Celery
backend           — gunicorn + UvicornWorker (ASGI), roda migrate + collectstatic no start
celery_worker     — processa tasks (hoje, infraestrutura pronta sem jobs definidos)
celery_beat       — agendador Celery
frontend          — SPA (Vue) já embutido na imagem, servido em HTTP puro pelo `serve` (sem nginx)
```

`backend`, `celery_worker`, `celery_beat` e `frontend` usam as imagens publicadas em `ghcr.io/<owner>/starchef-{backend,frontend}` (ver [§12](#12-cicd)), sempre fixas em `:latest` (a última tag de release publicada) — nada é buildado no host. Subir:

```
docker compose pull
docker compose up -d
```

Todos os serviços têm `mem_limit`/`cpus` (evita um vazamento em qualquer container derrubar o host inteiro) e log rotation (`json-file`, 10 MB × 5 arquivos). O backend roda com usuário não-root (uid 1000). `backend` e `frontend` publicam porta em HTTP puro, só em loopback por padrão (`BACKEND_PORT`/`FRONTEND_PORT`, `BACKEND_BIND`/`FRONTEND_BIND` no `.env.example`) — **este compose não tem nginx nem TLS**.

### Fluxo de request em produção

TLS, rate limiting por IP e o proxy same-origin ficam a cargo de um proxy reverso **externo** a este compose (nginx do host, Caddy, LB da nuvem etc. — ver [`infra/reverse-proxy.example.conf`](../infra/reverse-proxy.example.conf) como ponto de partida). O fluxo típico:

1. Cliente (browser ou app Flutter) → proxy reverso externo (TLS, rate limiting, mais restrito em `/auth/{login,refresh,password-reset}` e `/admin/login/`).
2. O proxy repassa `/` pro `frontend` (SPA estático via `serve`), e `/api/`, `/ws/`, `/health/`, `/admin/`, `/static/`, `/media/` pro `backend` (gunicorn) — tudo no mesmo domínio (same-origin, exigido pelos cookies `SameSite=Lax`).
3. `backend` roda Django em ASGI (`config.asgi:application`) via `UvicornWorker` — necessário porque HTTP e WebSocket (Channels) precisam do mesmo processo.
4. Estáticos do Django (admin/DRF) são servidos pelo próprio app via WhiteNoise; mídia (uploads) é servida por um `re_path` de fallback em `config/urls.py` — nenhum dos dois depende de volume compartilhado com outro serviço.

**Limite de confiança:** o backend confia em `X-Forwarded-Proto`/`X-Forwarded-For`/`Host` de quem se conectar nele (`SECURE_PROXY_SSL_HEADER`, `real_ip` de auditoria/throttle). Por isso a porta do backend não deve ficar acessível de fora do proxy reverso — por padrão ela só é publicada em loopback; se o proxy rodar em outra máquina, a porta liberada por firewall/security group deve ficar restrita ao IP dele.

### Segurança em produção

HSTS (30 dias + subdomínios + preload), `SECURE_SSL_REDIRECT`, cookies `Secure`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy` — estes três últimos headers são adicionados pelo proxy reverso externo, não pelo Django (ver `infra/reverse-proxy.example.conf` e [`FRONTEND.md`](FRONTEND.md)). Rate limiting em duas camadas: IP no proxy externo + DRF throttle por usuário/rota.

### Backup

Não roda mais como serviço do compose (produção ficou restrita a `postgres`/`redis`/`backend`/`frontend` + Celery). `infra/scripts/backup_postgres.sh` continua no repo pra quem quiser rodar `pg_dump` diário via cron do host ou reintroduzir como serviço — só não está mais ligado por padrão.

## 12. CI/CD

`.github/workflows/backend.yml` roda o job `test` em push/PR que tocam `backend/**`:

```
ruff check .
manage.py makemigrations --check --dry-run     (settings=test, SQLite)
pytest --cov=apps --cov-report=term-missing
```

O `ruff` está configurado (`backend/pyproject.toml`) só com a regra `F` (pyflakes — bugs reais: import/variável não usada, nome indefinido) por enquanto; `E501`/`I001` (linha longa/ordem de import) ficam de fora até uma passada dedicada de formatação, pra não gerar um diff gigante fora de contexto.

**Imagem de produção**: depois do `test` passar, o job `build-and-push-image` builda `backend/` (`REQUIREMENTS=production`) e publica em `ghcr.io/<owner>/starchef-backend`. Roda **só em tag `vX.Y.Z`** (ver [`FLUTTER_DESKTOP.md`§12](FLUTTER_DESKTOP.md#12-build-e-release) pra o fluxo completo de release) — nunca em PR nem em commit direto na `main`, pra backend/frontend/flutter saírem sempre com a mesma versão sem duplicar build a cada push. Sai `sha-<curto>` + `X.Y.Z` + `X.Y` + `latest`. Sem secrets no build — settings de produção são lidos em runtime via `.env`.

**Limpeza do GHCR**: o job `cleanup-old-images` roda depois e poda versões por idade (`dataaxiom/ghcr-cleanup-action`, `older-than: 1 year`) — qualquer versão (com tag ou não) com mais de 1 ano é apagada, exceto a que estiver marcada `latest` no momento (protegida sempre, não importa a idade).

## 13. Testes

188 testes hoje (`pytest -q`), ~72% de cobertura de linha (`--cov=apps`). Todas as 17 apps de domínio têm ao menos smoke tests (GET nos endpoints principais, autenticado, checando que a rota responde e não estoura 500) — 8 apps têm suítes mais profundas cobrindo regra de negócio (`accounts`, `customers`, `kitchen`, `menu`, `orders`, `payments`, `restaurants`, `sla`). `backend/conftest.py` centraliza as fixtures multi-tenant (`account`, `restaurant`, `branch`, `api_client` autenticado como gerente, `admin_client` autenticado como admin do tenant).

## 14. Admin (Django Admin + Unfold)

`django-unfold` dá uma UI mais moderna ao admin padrão do Django. Customização central em `apps/core/admin_mixins.py` — `TenantAdminMixin` filtra automaticamente queryset e FKs por tenant (superusuário escolhe a conta via `X-Account-ID`, os demais ficam presos à própria `profile.account`), preenche `account` ao salvar, ignora registros soft-deleted, e tem variantes para inlines (`TenantTabularInline`). Praticamente todos os apps de domínio têm `admin.py` customizado nesse padrão.

## 15. Referências

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — visão macro de camadas (mais antiga; este documento é a fonte mais completa/atual).
- [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md) — o que falta de **feature de negócio** (fiscal real, delivery, CRM etc.) — não confundir com prontidão técnica.
- [`FRONTEND.md`](FRONTEND.md) — como o SPA Vue consome esta API.
- [`FLUTTER_DESKTOP.md`](FLUTTER_DESKTOP.md) — como o PDV desktop consome esta API offline-first, e como o agente local se conecta às filas de impressão/balança descritas aqui.
