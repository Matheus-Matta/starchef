# StarChef Frontend — Guia Completo

> SPA Vue 3 que consome a API do backend Django ([`BACKEND.md`](BACKEND.md)): PDV, KDS, cardápio, caixa, relatórios e cadastros. Este documento cobre visão geral, arquitetura, como rodar em desenvolvimento e como funciona em produção.

## 1. Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Framework | Vue 3 (Composition API, `<script setup>`) |
| UI kit | PrimeVue 3.53 (tema `aura-light-teal`) + PrimeIcons |
| Estado global | Pinia |
| Roteamento | Vue Router 4 |
| Build | Vite 5, `vite-plugin-compression` (gzip + brotli) |
| HTTP | Axios, com interceptor de refresh de token |
| Testes | Vitest (jsdom) + `@vue/test-utils` |
| Lint | ESLint (`eslint-plugin-vue`) |
| Observabilidade | Sentry (`@sentry/vue`, opcional via `VITE_SENTRY_DSN`) |
| Servidor de produção | `serve` (Node) — só estáticos; TLS e proxy reverso ficam fora do compose |

Não há framework de estrutura por "features" — tudo vive em `src/views` (telas) e `src/components` (blocos reutilizáveis), sem uma pasta `src/features`.

## 2. Estrutura de pastas

```
frontend/
  src/
    assets/               imagens/ícones estáticos
    components/
      auth/                 componentes da tela de login
      data/                 StatCard, ReportDataTable
      display/               Card e afins
      form/                  AppFormField, AppFormSection, AppFormGrid, AppErrorSummary,
                              AppEntityDialog, AppAddressForm, AppDateRange, PermissionAccordion
      layout/                AppPageHeader e afins
      product/               ProductAddonsEditor, ProductVariationsEditor, RecipeItemsEditor
      AppIcon.vue            abstração de ícone (testado)
      NotificationBell.vue, GlobalSearch.vue, MobileBottomNav.vue
    composables/            useResourceList, useResourceForm, useRealtimeResource, useGlobalErrorHandler
    config/
      resources.js          schema declarativo do CRUD genérico (ver §5)
    layout/                 AppLayout.vue, Topbar.vue, Sidebar.vue, AuthLayout.vue
    router/                 index.js — rotas manuais + rotas geradas de resources.js
    services/               api.js (axios), realtimeService.js, dataExchangeService.js, reportService.js
    stores/                 auth.js, notifications.js  (só duas — Pinia)
    styles/
      tokens/                 colors.css, base.css, spacing.css, typography.css, fonts.css, density.css
      compact.css, motion.css, primevue-tokens.css
    utils/                  apiError.js, dateRange.js
    views/                  todas as telas (ver §3)
    sentry.js               init condicional do Sentry
    main.js                 bootstrap da app
    App.vue                 shell raiz (Toast/ConfirmDialog globais, error handler)
  public/                  runtime-config.js (default de dev), favicon etc.
  runtime-config.js.template  template usado no build de produção (ver §12)
  Dockerfile               build de produção (multi-stage → `serve`, sem nginx)
```

## 3. Rotas (`src/router/index.js`)

**Públicas**: `/login`, `/esqueci-senha`, `/redefinir-senha`.

**Autenticadas** (sob `AppLayout`):

| Rota | View | O que é |
|---|---|---|
| `/home` | `HomeView` | Home mobile-first: atalhos e navegação agrupada por módulo |
| `/relatorio-geral` | `DashboardView` | KPIs gerais |
| `/pdv` | `PdvView` | Tela de venda (PDV) |
| `/caixa` | `CashRegisterView` | Abertura/fechamento de caixa, sangria/suprimento — tela própria, fora do CRUD genérico |
| `/pedidos/:id/editar-itens` | `OrderEditView` | Wrapper fino sobre `PdvView` em modo edição |
| `/kds` | `KdsView` | Painel de cozinha ao vivo |
| `/kds-estacoes` | `KdsStationsView` | Cadastro de estações/colunas do KDS — tela própria |
| `/configuracao-focus` | `FocusNfeConfigView` | Credenciais, endpoints e webhook Focus isolados por conta |
| `/configuracao-cosmos` | `CosmosConfigView` | Token, User-Agent e ativação da busca fiscal Cosmos por conta |
| `/relatorios/{vendas,pedidos,produtos,pagamentos,garcons,restaurantes}` | `ReportsView` | Uma view compartilhada, `section` muda o conteúdo |
| `/<resource>`, `/<resource>/create`, `/<resource>/:id`, `/<resource>/:id/edit` | `ResourceListViewPro` / `ResourceFormView` | Geradas automaticamente a partir de `config/resources.js` |

O guard global (`router.beforeEach`) valida sessão via `authStore.validateSession()`, bloqueia rotas de módulo não contratado (`meta.module` vs `auth.hasModule`), e um listener de `auth:unauthorized` (disparado pelo interceptor do axios) força logout e redireciona ao login.

## 4. Telas principais

- **`PdvView.vue`** — o coração do sistema. Fluxo em passos (`restaurant → type → context → order`), com um gate de caixa aberto (`pdvGateLoading`/`pdvBlocked`) antes de liberar a venda. Painel de catálogo de produtos à esquerda, carrinho à direita (itens já enviados vs. pendentes, totais, ações de enviar/pagar). Aceita `editMode`/`orderId` para ser reaproveitada por `OrderEditView`.
- **`KdsView.vue`** — painel de cozinha: troca de estação, filtro por período, indicador "Ao vivo" com refresh manual (reforçado pelo WebSocket genérico, ver §6).
- **`KdsStationsView.vue`** — cadastro de estações/colunas do KDS, master-detail, mão feita (não usa o CRUD genérico).
- **`ReportsView.vue`** — componente único para todos os relatórios (`section: sales|orders|product|payment|waiter|restaurant`), com filtros de filial/categoria/setor, seletor de período, exportação CSV e StatCards de KPI.
- **`HomeView.vue`** — home mobile-first, atalhos e navegação condicionados a papel do usuário e módulos habilitados na conta.
- **`CashRegisterView.vue`** — gestão de caixa (estações, abrir/fechar sessão, sangria/suprimento, fluxo de aprovação gerencial reautenticando com token temporário). Mão feita, fora do CRUD genérico.

## 5. O sistema de CRUD genérico

`src/config/resources.js` declara ~24 recursos (produtos, categorias, clientes, ingredientes, receitas, mesas, comandas, papéis, permissões, SLA etc.) como schema:

```js
{
  name: "produtos",
  title: "Produtos",
  endpoint: "/menu/products/",
  module: "logistica",        // opcional — gating por módulo
  columns: [{ key: "name", label: "Nome" }, { key: "sale_price", label: "Preço", type: "money" }],
  formFields: [{ name: "name", label: "Nome", type: "text", required: true, section: "Geral" }],
  pro: { primaryAction: {...}, quickFilters: [...], rowActions: [...] }  // recursos avançados da tabela Pro
}
```

`router/index.js` gera as 4 rotas (list/create/view/edit) para **todo** recurso, exceto os que têm tela própria (`CUSTOM_RESOURCES = ["caixa", "kds-estacoes"]`). A migração para a tabela "Pro" (`ResourceListViewPro`) está **completa** — não existe mais `ResourceListView.vue` clássico no código; todo recurso, incluindo mesas e produtos, usa o padrão novo.

Dois composables sustentam isso:
- **`useResourceList.js`** — paginação/ordenação/busca server-side para `ResourceListViewPro`.
- **`useResourceForm.js`** — carrega o registro, monta o form a partir de `formFields`, faz POST/PATCH, mapeia erros de validação do backend para os campos.

Em **Ingredientes**, a ação “Cadastrar em lote” abre um formulário repetível e
salva todas as linhas numa única operação atômica. A Logística também oferece o
CRUD de **Fornecedores**; o fornecedor padrão fica vinculado ao insumo. Na tela
de entrada, selecionar o insumo preenche sua unidade, fornecedor e, quando
disponível, o último custo médio, mantendo os campos editáveis para a compra
atual.

Na criação de um perfil fiscal, `CosmosFiscalAssist.vue` observa o nome e,
quando a integração da conta está ativa, consulta a Cosmos depois de uma pausa
curta na digitação. NCM e CEST encontrados preenchem o formulário para revisão,
sem sobrescrever campos alterados manualmente. O mesmo componente aparece no
diálogo de criação rápida aberto pelo cadastro de produto.

No recurso **Restaurantes**, o campo “Definir senha de ações do caixa” recebe a
senha que será digitada no PDV (por exemplo, `123`). O usuário nunca copia ou
cola uma hash: a API gera PBKDF2-SHA256. Em uma edição, o campo volta vazio e
deixá-lo assim preserva a senha atual, pois o texto e a hash nunca retornam no
payload do CRUD.

## 6. Tempo real

Dois canais WebSocket independentes, ambos same-origin (`/ws/...`, proxiado pelo Vite em dev e pelo proxy reverso externo em produção):

- **`stores/notifications.js`** conecta em `/ws/notifications/` — sino de notificações, reconecta sozinho após 4s se cair. Mensagens: `{event:"notification", payload}` (nova notificação) e `{event:"connected", payload:{unread}}` (sync inicial do contador).
- **`services/realtimeService.js`** (singleton) conecta em `/ws/realtime/` — canal genérico de eventos de modelo do backend (`apps/realtime`, ver [`BACKEND.md`](BACKEND.md#6-websocket--tempo-real)). Reconecta com backoff exponencial, heartbeat de 25s, pub/sub por `event` com wildcard `"*"`. A URL do socket é derivada da **origem da API** (`RUNTIME_CONFIG.API_URL`), não da origem da página: com a API num subdomínio próprio (`api.dominio`), o `/ws/` só existe atrás do proxy dela. `RUNTIME_CONFIG.WS_URL` sobrescreve quando o WebSocket fica num host à parte. Consumido via `useRealtimeResource.js`, que filtra por nome de recurso e faz debounce (120ms padrão) antes de disparar um refresh de lista/board.

## 7. Autenticação no frontend

- **Login**: `LoginScreen.vue` → `authStore.login()` → `services/api.js` (o backend grava os cookies httpOnly); a store então chama `fetchMe()` para popular `user`.
- **Restauração de sessão**: o guard de rota chama `auth.validateSession()`, que confia num cache de 30s se já validado, senão bate em `/auth/me/`; em 401, tenta um `refreshAccessToken()` explícito + retry antes de desistir.
- **Logout**: `auth.logout()` chama `/auth/logout/` e limpa o estado local; também é disparado globalmente pelo evento `auth:unauthorized` (do interceptor do axios) que limpa a sessão e redireciona para `/login?next=...`.
- **Gating por módulo/papel**: `auth.hasModule(nome)` — superusuário sempre passa, os demais checam `user.enabled_modules`. Usado no guard de rota (bloqueia acesso direto a rotas de módulo desabilitado) e na UI (menus, campos de recurso com `module`). Permissões finas de negócio (papel → permissões) são modeladas no backend e editadas via o próprio CRUD genérico (`PermissionAccordion.vue`).

## 8. Tratamento de erro e observabilidade

- **`utils/apiError.js`** normaliza qualquer erro do axios/DRF: distingue rede/400/401/403/404/409/422/500+, separa erros de campo (`fieldErrors`) da mensagem geral, sempre devolve uma mensagem compreensível.
- **Handler global**: `main.js` define `app.config.errorHandler`, que despacha um `CustomEvent("app:unhandled-error")`. `App.vue` usa `composables/useGlobalErrorHandler.js` para escutar esse evento e mostrar um Toast — sem isso, um erro não tratado em qualquer componente quebrava a tela em silêncio.
- **Sentry** (`src/sentry.js`): só inicializa se `VITE_SENTRY_DSN` estiver definido (`.env`) — sem DSN, zero overhead, comportamento idêntico a hoje.

## 9. Tema e design tokens

**A densidade responde ao tamanho da tela** (`tokens/density.css`). Não é
zoom: escalar a página inteira borra o texto e encolhe o alvo do clique junto.
Quem muda são os tokens, em três degraus explícitos — até 1280 px tudo fica
mais junto (cabe mais linha no notebook), a base é o 1366×768 da operação, e a
partir de 1600 px tudo respira, porque sobra espaço e o operador está mais
longe da tela.

Altura de controle, tipografia de formulário, respiro, célula de tabela,
largura da barra lateral e altura do cabeçalho saem TODOS daí. `styles.css` não
redefine nenhum desses tokens: dois donos para o mesmo valor é armadilha — o de
baixo vence, em silêncio, e foi assim que a barra lateral ficou grande depois
de os controles terem sido reduzidos.

Os degraus são passos, não `clamp()` com `vw`: uma altura de 31,4 px não é
legível para quem for mexer na régua depois.

**Altura dos campos.** Todo controle de UMA LINHA — texto, select, multi-select,
calendário, senha, número e botão — tem a MESMA altura, fixada em
`--control-h` (`tokens/density.css`) e aplicada em `compact.css`.

Antes só o `.p-inputtext` tinha altura fixa; o resto tinha apenas
`min-height`. Como cada componente do PrimeVue traz o próprio padding interno,
o select parava mais alto que o campo de texto e o calendário mais alto que os
dois — a linha do formulário saía em escadinha. Os invólucros (`.p-calendar`,
`.p-password`, `.p-inputnumber`) também precisam que o `.p-inputtext` de
dentro ocupe `height: 100%`, senão o campo tem o tamanho certo e o texto
flutua fora do centro.

A `textarea` fica de fora de propósito: ela cresce com o texto, e travar a
altura esconderia o que o operador acabou de escrever. `density.test.js` fixa
essas regras.

Toggle claro/escuro no `Topbar.vue` (`toggle-theme`), estado via `provide/inject("theme")` em `AppLayout.vue`, aplicado como `data-theme` na raiz do app. Tokens em `src/styles/tokens/` (`colors.css` com blocos `[data-theme="light"|"dark"]`, `spacing.css`, `typography.css`, `density.css` — escala compacta) e `primevue-tokens.css` (mapeia variáveis de componente do PrimeVue para o sistema de tokens).

## 10. Como rodar em desenvolvimento

```bash
npm --prefix frontend install
npm run dev:frontend      # a partir da raiz do monorepo — atalho para: npm --prefix frontend run dev
# ou, dentro de frontend/:
npm run dev               # vite, porta 5173
npm run build              # build de produção
npm run lint                # eslint src --ext .js,.vue
npm run test                 # vitest run
npm run preview               # serve o build localmente
```

`vite.config.js` carrega o `.env` da **raiz do monorepo** (não de `frontend/`) — um único arquivo de env compartilhado entre backend/frontend/Flutter. Em dev, o servidor Vite faz proxy de `/api` e `/ws` para `VITE_BACKEND_TARGET` (default `http://localhost:8001`) — assim o app sempre chama a própria origem, e os cookies httpOnly (`SameSite=Lax`) funcionam mesmo atrás de um devtunnel.

## 11. Configuração / variáveis de ambiente

Vem do mesmo `.env` documentado em [`BACKEND.md`](BACKEND.md#10-configuração--variáveis-de-ambiente) (raiz do monorepo). As relevantes para o frontend:

- `VITE_BACKEND_TARGET` — alvo do proxy do Vite em dev.
- `API_URL` — usado no build de produção (`docker-compose.yml`), normalmente `/api/v1` (same-origin, sem CORS).
- `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`, `VITE_SENTRY_TRACES_SAMPLE_RATE` — opcionais, Sentry do frontend (projeto separado do Sentry do backend).

Em produção, a URL da API não é fixada no build: `runtime-config.js.template` vira `runtime-config.js` via `sed` num `docker-entrypoint.sh` próprio, executado no start do container (`window.RUNTIME_CONFIG = { API_URL: "...", WS_URL: "..." }` — `WS_URL` é opcional e fica vazio quando o WebSocket acompanha a origem da API), permitindo promover a mesma imagem entre ambientes sem rebuild.

## 12. Produção

**Build** (`frontend/Dockerfile`, multi-stage, sem nginx):

1. `node:24-alpine` — `npm ci` + `npm run build` (sourcemaps desligados, `console`/`debugger` removidos pelo esbuild, chunks separados por vendor: `primevue`, `vue`, `axios`).
2. `node:24-alpine` (stage de runtime) — instala o pacote `serve` (versão pinada), copia só `dist/`, o template de runtime-config, `serve.json` (cache headers) e `docker-entrypoint.sh`.

**Serving**: o container roda `docker-entrypoint.sh` (gera `dist/runtime-config.js` a partir do template) e então `serve -s dist -l 8080 -c serve.json` — só serve os estáticos da SPA em HTTP puro, com fallback de rota (`-s`) e os `Cache-Control` de `serve.json` (`index.html`/`runtime-config.js` sem cache, `assets/` imutável 1 ano). **Não há mais proxy nem TLS neste container**: quem faz proxy same-origin de `/api/`, `/ws/`, `/health/`, `/admin/` para o `backend` (gunicorn), rate limiting por IP, compressão e headers de segurança (`Content-Security-Policy` etc.) é um proxy reverso **externo** ao `docker-compose.yml` — ver [`infra/reverse-proxy.example.conf`](../infra/reverse-proxy.example.conf), que preserva a mesma política de CSP (`default-src 'self'; connect-src 'self' wss:; style-src 'self' 'unsafe-inline'` — o `unsafe-inline` de estilo é necessário porque o PrimeVue injeta estilo inline via JS) como ponto de partida pra montar esse proxy.

Subir tudo: `docker compose pull && docker compose up -d` (baixa as imagens publicadas de backend/frontend, nada é buildado no host; `frontend` e `backend` ficam em HTTP puro, publicados só em loopback por padrão — ver [`BACKEND.md`](BACKEND.md#11-produção) para o que mais sobe e o fluxo de request completo).

## 13. Testes e CI

`npm run test` (Vitest + jsdom): hoje cobre `utils/apiError.js` (todos os casos de status HTTP) e `components/AppIcon.vue` (smoke de render). `.github/workflows/frontend.yml` roda o job `build` em push/PR tocando `frontend/**`: `npm ci` → `lint` → `test` → `build` → `npm audit --production`.

**Imagem de produção**: depois do `build` passar, o job `build-and-push-image` builda `frontend/` e publica em `ghcr.io/<owner>/starchef-frontend`. Roda **só em tag `vX.Y.Z`** (ver [`FLUTTER_DESKTOP.md`§12](FLUTTER_DESKTOP.md#12-build-e-release) pra o fluxo completo de release) — nunca em PR nem em commit direto na `main`, pra backend/frontend/flutter saírem sempre com a mesma versão sem duplicar build a cada push. Sai `sha-<curto>` + `X.Y.Z` + `X.Y` + `latest`. Sem build args/secrets — a mesma imagem serve qualquer ambiente (§11 acima).

**Limpeza do GHCR**: o job `cleanup-old-images` roda depois e poda versões por idade (`dataaxiom/ghcr-cleanup-action`, `older-than: 1 year`) — qualquer versão (com tag ou não) com mais de 1 ano é apagada, exceto a que estiver marcada `latest` no momento (protegida sempre, não importa a idade).

## 14. Referências

- [`BACKEND.md`](BACKEND.md) — a API que este frontend consome.
- [`FLUTTER_DESKTOP.md`](FLUTTER_DESKTOP.md) — o outro cliente da mesma API (PDV desktop offline-first); não compartilha código com este frontend, mas compartilha o `.env` da raiz e os mesmos contratos de API.
