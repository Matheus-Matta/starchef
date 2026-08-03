# StarChef

Plataforma multi-tenant para a operação de restaurantes, com retaguarda web, PDV, KDS, caixa, impressão e integrações com dispositivos locais.

## Estado atual

A versão atual reúne três aplicações no mesmo repositório:

- **Backend Django/DRF:** API REST, autenticação, regras de negócio, WebSockets e tarefas assíncronas.
- **Retaguarda Vue 3:** cadastros, dashboard, PDV web, caixa, pedidos, relatórios e KDS.
- **PDV Flutter para Windows:** operação de balcão, leitura offline da configuração, autenticação de caixa e agente local de impressoras/balanças.

Os dados são isolados por conta, restaurante e filial. Limites de restaurantes e usuários podem ser definidos por plano e sobrescritos na conta.

## Principais recursos

- login JWT com access token em memória e refresh token em cookie `HttpOnly`;
- usuários, papéis, permissões granulares e módulos habilitados;
- restaurantes, filiais, setores, mesas e comandas reutilizáveis com código de barras/QR;
- cardápio, variações obrigatórias, adicionais, ingredientes e fichas técnicas;
- pedidos de mesa, comanda, balcão, retirada e delivery;
- rodadas de produção, cancelamento/cortesia de itens, pagamento parcial e estorno;
- KDS em tempo real, com estações e colunas configuráveis por templates;
- caixa por estação, sangria, suprimento, fechamento e aprovação gerencial;
- recibos, estrutura fiscal, filas de impressão e integração com impressoras e balanças;
- notificações persistidas e entregues por WebSocket;
- dashboard, relatórios de vendas, alertas de estoque, SLA e trilha de auditoria;
- menu público por slug.

## Arquitetura

```text
Retaguarda Vue 3 ─┐
PDV Flutter/Win ──┼── REST /api/v1 + WebSocket /ws ── Django ASGI
Menu público ─────┘                                      │
                                      ┌──────────────────┼──────────────┐
                                  PostgreSQL           Redis          Celery
                                  transações      cache/channels    jobs/beat
```

Em desenvolvimento, o backend pode usar SQLite, cache e Channels em memória e Celery em modo eager. Em produção, o Compose usa PostgreSQL, Redis, Gunicorn com worker Uvicorn, Celery e Nginx.

## Estrutura

```text
backend/
  apps/
    accounts/       contas, planos, usuários, papéis e permissões
    core/           tenancy, autenticação, auditoria e infraestrutura comum
    restaurants/    restaurantes, filiais, mesas, comandas e delivery
    menu/           cardápio, produtos, variações, adicionais e receitas
    orders/         pedidos, itens, rodadas e fluxo de pagamento
    kitchen/        estações, colunas e consultas do KDS
    payments/       métodos, estações de caixa, sessões e movimentos
    printers/       impressoras, balanças e jobs de impressão
    notifications/  notificações persistidas e WebSocket
    customers/ invoices/ stock/ reports/ sla/ integrations/
  config/           settings, URLs, ASGI, WSGI e Celery
  tests/            testes de integração
frontend/           SPA Vue 3 + PrimeVue + Pinia + Vite
flutter/            PDV Flutter desktop para Windows
infra/              configuração Nginx de produção
docs/               documentação complementar
DOC.md              referência técnica da versão atual
```

## Início rápido local

Pré-requisitos: Python, Node.js/npm e, para o PDV desktop, Flutter com suporte a Windows.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements\development.txt
npm --prefix frontend install
npm run migrate
npm run seed
npm run dev
```

`npm run dev` inicia o backend em `http://localhost:8001` e o Vite em `http://localhost:5173`. Também é possível iniciar os processos separadamente:

```powershell
npm run dev:backend
npm run dev:frontend
npm run dev:flutter
```

O seed cria a conta de demonstração, restaurante, filial e dados operacionais. Credenciais locais:

```text
usuário: admin
senha:   admin12345
```

Para reconstruir um SQLite local inconsistente, mantendo backup automático:

```powershell
.\.venv\Scripts\python backend\manage.py seed_demo --reset-sqlite
```

## Docker (produção)

`docker-compose.yml` sobe PostgreSQL, Redis, backend, workers Celery e frontend a partir das imagens publicadas pelo CI em `ghcr.io` (nada builda no host — ver [`.github/workflows/backend.yml`](.github/workflows/backend.yml) e [`frontend.yml`](.github/workflows/frontend.yml), que só publicam em tag de release):

```bash
cp .env.example .env
# preencha segredos, domínio, origens confiáveis e certificados
docker compose pull
docker compose up -d
```

Não publica PostgreSQL nem Redis para fora, executa migrations e `collectstatic` no start, roda com usuário não-root, e expõe só o `frontend` (nginx) em `80/443`.

## URLs úteis

- retaguarda: `http://localhost:5173/`
- API: `http://localhost:8001/api/v1/`
- Swagger: `http://localhost:8001/api/schema/swagger-ui/`
- Django Admin: `http://localhost:8001/admin/`
- health check: `http://localhost:8001/health/`

No Docker de desenvolvimento, o backend é publicado em `http://localhost:8000`.

## Qualidade e testes

```powershell
.\.venv\Scripts\python backend\manage.py check
.\.venv\Scripts\pytest backend
npm --prefix frontend run lint
npm --prefix frontend run build
Push-Location flutter; flutter analyze; flutter test; Pop-Location
```

## Comando administrativo

```powershell
# Sincroniza o catálogo de permissões e papéis padrão
.\.venv\Scripts\python backend\manage.py sync_permissions
```

Usuários e seus vínculos de tenant podem ser administrados pela retaguarda ou pelo Django Admin.

Consulte [DOC.md](DOC.md) para arquitetura, domínios, API, segurança, configuração e fluxos operacionais.

## Licença

Este é um software proprietário, com todos os direitos reservados. Cópia, redistribuição, sublicenciamento, oferta como serviço e revenda são proibidos sem autorização prévia e expressa do titular.

Consulte o arquivo [LICENSE](LICENSE). A presença do código neste repositório não concede uma licença open source.
