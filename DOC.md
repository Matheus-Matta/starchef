# StarChef — Documentação técnica

> Atualizado em 26/07/2026 para a versão atual do repositório.

## 1. Visão geral

StarChef é uma plataforma multi-tenant para operação e gestão de restaurantes. A solução cobre retaguarda, ponto de venda, cozinha, caixa, estoque, impressão e dispositivos locais.

| Aplicação | Responsabilidade |
|---|---|
| Backend Django | API, autenticação, tenancy, regras de negócio, WebSockets e jobs |
| Frontend Vue | Retaguarda, cadastros, PDV web, caixa, KDS e relatórios |
| Flutter Windows | PDV desktop e agente local de impressoras/balanças |

Tipos de atendimento: mesa, comanda, balcão, retirada e delivery.

## 2. Arquitetura e execução

```text
Vue/Vite ou Nginx ─┐
Flutter Windows ───┼── HTTP REST ───────┐
                   └── WebSocket ───────┤
                                       ▼
                                Django ASGI/DRF
                                  │    │    │
                         PostgreSQL  Redis  Celery
```

- A API fica sob `/api/v1/`.
- O KDS usa `/ws/kitchen/<branch_id>/<sector>/`.
- Notificações usam `/ws/notifications/`.
- Em desenvolvimento, `DEBUG=True` seleciona `config.settings.development`; SQLite e serviços em memória são suportados.
- Em produção, `config.settings.production` usa PostgreSQL, Redis, cookies seguros, Gunicorn/Uvicorn e Nginx.
- `manage.py runservices` inicia backend e frontend juntos e encerra ambos no `Ctrl+C`.

## 3. Tecnologias

Backend: Python, Django 5, Django REST Framework, SimpleJWT, Channels/Daphne, Celery, PostgreSQL, Redis, drf-spectacular, django-filter, django-unfold e pytest.

Frontend: Vue 3, Vue Router, Pinia, PrimeVue/PrimeIcons, Axios, Vite e ESLint.

Desktop: Flutter/Dart, `http`, `flutter_secure_storage`, `window_manager`, SVG e `crypto`.

Infraestrutura: Docker Compose, Nginx, Gunicorn com `UvicornWorker`, volumes persistentes e health checks.

As versões exatas estão em `backend/requirements/*.txt`, `frontend/package.json` e `flutter/pubspec.yaml`.

## 4. Multi-tenancy

```text
Account
└── Restaurant
    └── Branch
        └── dados operacionais
```

- `TenantBaseModel` adiciona conta, auditoria, timestamps e exclusão lógica.
- `TenantModel` adiciona restaurante e filial aos dados operacionais.
- O `TenantMiddleware` resolve o perfil e o escopo da requisição.
- Viewsets usam mixins de filtragem para evitar acesso cruzado entre tenants.
- `TenantResponseSafetyMiddleware` adiciona uma barreira adicional contra respostas fora do escopo.
- Superusuários podem operar recursos globais; usuários comuns ficam limitados ao perfil.
- `Account.max_restaurants` e `Account.max_users` permitem limites específicos, com fallback para o plano.

## 5. Domínios e modelos

### Accounts

- `Plan`: limites, módulos e recursos do plano.
- `Account`: tenant raiz, estado da assinatura e limites sobrescritos.
- `Subscription`: período e estado da assinatura.
- `Permission`: catálogo global, agrupado para exibição.
- `Role`: papel do tenant com conjunto de permissões.
- `UserProfile`: vínculo do usuário com conta, restaurante, filial e papel.
- `GlobalSystemConfig`: configuração administrativa global.

O comando `sync_permissions` mantém catálogo, grupos e papéis padrão sincronizados.

### Restaurants

- `Restaurant` e `Branch`: identidade, configurações operacionais, impressão e fiscal.
- `TableSector` e `Table`: salão, capacidade, estado e código escaneável.
- `Command`: cartão reutilizável, numerado por restaurante, com código QR/barra.
- `DeliveryZone` e `Deliveryman`: taxa, prazo e entregador.

Restaurantes podem exigir caixa aberto para vender e definir senha de autorização de caixa. Mesas e comandas podem ter códigos gerados em lote.

### Menu

- categorias, produtos, variações, adicionais, ingredientes, receitas e itens de receita;
- menus e seus itens;
- produto pode exigir a escolha de uma variação;
- produto pode ser direcionado a um setor de produção;
- adicionais são vinculados explicitamente ao produto.

### Orders

- `Order`: conta comercial aberta, tipo de atendimento, totais, pagamento e entrega.
- `OrderBatch`: rodada enviada à produção.
- `OrderItem`: item, variação, quantidade, status e coluna KDS.
- `OrderItemAddon`: adicionais do item.

O status comercial do pedido, o status de pagamento e o status de produção dos itens são ciclos relacionados, mas independentes. Isso permite novas rodadas, pagamento parcial e preparação simultânea.

### Kitchen e SLA

- `KdsStation`: quadro por restaurante/filial, setores e SLA.
- `KdsColumn`: colunas livres, ordenadas, com marcadores de entrada e conclusão.
- templates criam estações comuns rapidamente;
- itens podem mudar de status ou ser movidos entre colunas;
- SLAs podem ter limites e regras por nível operacional.

### Payments

- `PaymentMethod`: dinheiro, cartão, PIX, voucher ou outro.
- `Payment`: valor, troco, subtipo de cartão, status e chave de idempotência.
- `CashStation`: ponto físico/lógico, operadores e limite.
- `CashRegister`: sessão de caixa, dispositivo, valores, divergência e aprovação.
- `CashMovement`: abertura, venda, sangria, suprimento, ajuste, estorno e fechamento.

Operações sensíveis podem exigir autorização gerencial. A senha é validada no servidor e o PDV Flutter mantém um verificador seguro para cenários offline autorizados.

### Printers e scales

- `Printer`: conexão, setor, tipo e configuração de impressão.
- `PrintJob`: fila persistida, tentativas e resultado.
- `Scale`: configuração e lease do agente local.
- `ScaleReading`: leituras, vínculo opcional ao pedido e metadados.

O agente Flutter consulta dispositivos disponíveis, mantém templates em cache e confirma sucesso ou falha dos jobs.

### Notifications

`Notification` armazena destinatário, categoria, nível, conteúdo, rota, entidade de origem e estado de leitura. Eventos são persistidos e enviados ao usuário autenticado em tempo real.

### Demais domínios

- `customers`: clientes e endereços.
- `stock`: locais, movimentos e alertas.
- `invoices`: configuração/perfil fiscal, emissão, cancelamento e impressão.
- `reports`: dashboard e vendas.
- `core`: auditoria, códigos, cookies, autenticação e exceções padronizadas.

## 6. API

### Autenticação

| Método | Endpoint | Uso |
|---|---|---|
| POST | `/api/v1/auth/login/` | login |
| POST | `/api/v1/auth/refresh/` | renova sessão pelo cookie |
| POST | `/api/v1/auth/verify/` | verifica token |
| GET | `/api/v1/auth/me/` | usuário, escopo, módulos e permissões |
| POST | `/api/v1/auth/logout/` | revoga/limpa a sessão |

### Recursos REST

O router expõe:

```text
accounts, plans, subscriptions, system-config
users, roles, permissions
restaurants, branches, tables/sectors, tables, commands
delivery/zones, delivery/deliverymen
customers, customers/addresses
menu/categories, menu/products, menu/addons, menu/variations
menu/ingredients, menu/recipes, menu/recipe-items, menu/menus, menu/menu-items
orders, orders/items
sla
kitchen/stations, kitchen/columns, kitchen/items, kitchen/orders
payments/methods, payments, cash-register, cash-stations
fiscal/config, fiscal/profiles, invoices
printers, print-jobs, scales, scales/readings
stock/locations, stock/movements
notifications
```

### Ações importantes

- pedidos: `open-table`, `open-command`, `items`, `send-to-kitchen`, `pay`, `payments`, `close`, `cancel` e `print`;
- itens: cancelamento, cortesia e mudança de status;
- caixa: `open`, `current`, `close`, `withdrawal`, `supply` e aprovação;
- KDS: templates, criação por template, mudança de status e movimento entre colunas;
- impressoras: templates, teste de conexão e atualização de jobs;
- balanças: claim/release do agente, última leitura, pesagem e vínculo ao pedido;
- notificações: contagem não lida, marcar uma ou todas como lidas;
- fiscal: emissão, impressão e cancelamento.

Endpoints adicionais:

| Endpoint | Descrição |
|---|---|
| `/api/v1/reports/dashboard/` | indicadores operacionais |
| `/api/v1/reports/sales/` | relatório de vendas |
| `/api/v1/stock/alerts/` | alertas de estoque |
| `/api/v1/public/menu/<slug>/` | menu público |
| `/api/schema/` | OpenAPI |
| `/api/schema/swagger-ui/` | Swagger UI |
| `/health/` | health check |

## 7. Frontend Vue

Telas próprias:

- Home e relatório geral;
- PDV e edição de itens do pedido;
- controle de caixa;
- KDS e configuração de estações;
- relatórios;
- busca global e central de notificações.

Cadastros definidos em `frontend/src/config/resources.js` geram rotas de lista, criação, detalhe e edição. A navegação respeita módulos habilitados e o guard bloqueia acesso direto a módulos indisponíveis.

Autenticação:

- access token mantido em memória;
- refresh token em cookie `HttpOnly`;
- interceptor tenta renovação coordenada após `401`;
- sessão inválida dispara logout global;
- cabeçalhos de restaurante e filial representam o escopo ativo.

## 8. PDV Flutter para Windows

O aplicativo em `flutter/` é uma superfície operacional dedicada. Ele inclui:

- login e restauração segura de sessão;
- seleção de restaurante/filial;
- abertura e edição de pedidos;
- carrinho e apresentação desacoplados da camada de dados;
- caixa e autorização de operações;
- armazenamento offline controlado;
- inventário de dispositivos locais;
- seleção de impressora e cache de templates;
- agente local de impressão/balança;
- instalador Inno Setup em `flutter/windows/installer/starchef_pdv.iss`.

Configuração da API:

```powershell
cd flutter
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8001/api/v1
```

Sem `API_BASE_URL`, o app procura `VITE_API_BASE_URL` ou `API_BASE_URL` em um `.env`; o caminho pode ser indicado por `--dart-define=STAR_CHEF_ENV_PATH=...`. O fallback é `http://localhost:8000/api/v1`.

## 9. Fluxos operacionais

### Pedido e cozinha

1. O operador abre ou recupera pedido por mesa/comanda, ou cria balcão/retirada/delivery.
2. Inclui itens, variações e adicionais.
3. `send-to-kitchen` cria uma rodada e encaminha cada item ao setor/estação.
4. KDS recebe atualização WebSocket e posiciona o card na coluna de entrada.
5. O item percorre as colunas; a coluna final conclui sua produção.
6. Novos itens podem formar rodadas posteriores sem reabrir os anteriores.

### Pagamento

1. O pedido calcula subtotal, descontos, taxas, total pago e saldo.
2. Cada pagamento usa método, valor e chave idempotente.
3. Pagamentos parciais mantêm saldo aberto.
4. Ao quitar/fechar, mesa ou comanda é liberada conforme a regra operacional.
5. Remoção/estorno atualiza caixa e auditoria.

### Caixa

1. O operador abre uma sessão para filial/estação/dispositivo.
2. Vendas em dinheiro geram movimentos vinculados.
3. Sangria e suprimento registram motivo, destino e autorização.
4. Fechamento compara valor esperado e contado.
5. Divergências ou regras do restaurante podem enviar a sessão para aprovação.

## 10. Segurança

- JWT com blacklist e refresh em cookie `HttpOnly`;
- cookies `Secure` e política `SameSite` configuráveis em produção;
- CSRF, CORS, hosts e origens WebSocket validados;
- rate limits distintos para anônimo, usuário, login, refresh, menu público e aprovação de caixa;
- chaves de idempotência em pagamentos;
- permissões granulares por ação;
- isolamento de queryset e validação de tenant na resposta;
- segredos somente por variáveis de ambiente;
- PostgreSQL e Redis sem portas públicas no Compose de produção.

Nunca use os segredos ou credenciais demo em produção.

## 11. Configuração

Copie `.env.example` para `.env` no desenvolvimento. Categorias principais:

```text
DJANGO_SETTINGS_MODULE, DJANGO_SECRET_KEY, DJANGO_DEBUG
USE_SQLITE_DATABASE, SQLITE_DB_NAME, USE_LOCAL_MEMORY_SERVICES
DJANGO_ALLOWED_HOSTS, DJANGO_CORS_ALLOWED_ORIGINS
POSTGRES_*, REDIS_URL, CELERY_*
VITE_API_BASE_URL
THROTTLE_RATE_*
```

`.env.example` documenta as variáveis de produção (TLS/proxy, cookies seguros, Sentry, Gunicorn, origens confiáveis, tags de imagem) — é o que `docker-compose.yml` lê via `.env`. Nunca versionar o `.env` real.

## 12. Instalação e comandos

### Desenvolvimento local

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements\development.txt
npm --prefix frontend install
.\.venv\Scripts\python backend\manage.py migrate
.\.venv\Scripts\python backend\manage.py seed_demo
npm run dev
```

Atalhos na raiz:

| Comando | Resultado |
|---|---|
| `npm run dev` | backend e frontend |
| `npm run dev:backend` | Django em `:8001` |
| `npm run dev:frontend` | Vite |
| `npm run dev:flutter` | Flutter Windows |
| `npm run migrate` | migrations |
| `npm run seed` | dados demo |
| `npm run shell` | Django shell |

`seed_demo --migrate` aplica migrations antes do seed. `seed_demo --reset-sqlite` cria backup e refaz a base local.

### Docker (produção)

```bash
cp .env.example .env
docker compose pull
docker compose up -d
```

`docker-compose.yml` só sobe as imagens publicadas pelo CI (`ghcr.io`) — exige preencher o `.env`, configurar domínio/origens e fornecer certificados em `infra/certs`.

## 13. Testes e validação

```powershell
.\.venv\Scripts\python backend\manage.py check
.\.venv\Scripts\pytest backend
npm --prefix frontend run lint
npm --prefix frontend run build
Push-Location flutter
flutter analyze
flutter test
Pop-Location
```

Os testes backend cobrem tenancy, permissões, autenticação/autorização de caixa, pedidos, mesas/comandas, KDS, impressão e balanças. O Flutter possui testes de configuração, cliente HTTP, senha de caixa e apresentação de pedidos.

## 14. Implantação

O `docker-compose.yml`:

- puxa as imagens imutáveis publicadas pelo CI (`ghcr.io`, uma tag de release por vez — nada builda no host);
- executa migrations e coleta de estáticos;
- inicia backend ASGI com Gunicorn/Uvicorn;
- inicia worker e beat do Celery;
- serve SPA, estáticos e mídia pelo Nginx;
- faz proxy de HTTP e WebSocket;
- publica apenas `80` e `443`;
- usa volumes para banco, Redis, mídia e estáticos.

Antes de publicar, execute testes/builds, troque todas as credenciais e valide `/health/`, login, WebSockets e impressão. Backup do PostgreSQL não roda automático por padrão — ver `infra/scripts/backup_postgres.sh`.

## 15. Escopo futuro

Permanecem como evolução, e não como garantia da versão atual:

- provedores fiscais e gateways de pagamento reais;
- integrações completas com marketplaces;
- sincronização offline transacional mais ampla;
- automação de backup/restore e observabilidade operacional;
- cobrança automática de assinatura SaaS.

## 16. Licença e propriedade intelectual

StarChef é software proprietário. O acesso ao repositório não concede permissão para copiar, distribuir, modificar, sublicenciar, oferecer como serviço ou revender o sistema.

Os termos completos estão em `LICENSE`. Dependências de terceiros continuam submetidas às respectivas licenças.
