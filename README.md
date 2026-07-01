# StarChef

Monorepo para um MVP de gestao de restaurante com Django REST Framework no backend e Vue 3 no frontend.

## Visao geral

StarChef foi organizado para operar restaurante, lanchonete, pizzaria, hamburgueria, delivery, retirada, atendimento de balcao, mesas e comandas. O MVP prioriza fluxo diario:

1. login JWT;
2. selecao de restaurante/filial por perfil;
3. abertura de pedido por mesa, comanda, balcao, retirada ou delivery;
4. envio de itens para cozinha via WebSocket;
5. painel KDS em tempo real;
6. fechamento de conta, pagamento, caixa e recibo simples;
7. auditoria basica e dashboard operacional.

O desenho ja separa dados por restaurante e filial para evoluir para SaaS multi-restaurante e multi-filial.

## Diagrama textual

```text
Browser/PWA futuro
  |-- Vue 3 + PrimeVue + Pinia + Router
  |-- Axios REST /api/v1
  |-- WebSocket /ws/kitchen/{branch_id}/{sector}/
        |
        v
Nginx (producao)
  |-- frontend estatico
  |-- reverse proxy HTTP -> Django ASGI
  |-- reverse proxy WS   -> Django ASGI
        |
        v
Django ASGI
  |-- DRF + JWT + OpenAPI
  |-- Channels consumers KDS
  |-- Apps de dominio: orders, menu, payments, stock, printers
        |
        |-- PostgreSQL: dados transacionais
        |-- Redis: cache, channel layer, broker Celery
        |-- Celery worker: tarefas async, impressao, relatorios
        |-- Celery beat: tarefas agendadas, backups, health routines
```

## Estrutura

```text
backend/
  apps/
    accounts/      perfis, papeis e permissoes
    core/          base models, auditoria, permissoes, paginacao
    customers/     clientes e enderecos
    invoices/      recibo nao fiscal e arquitetura fiscal futura
    kitchen/       endpoints do KDS
    menu/          cardapio, produtos, adicionais e ficha tecnica
    orders/        pedidos, itens, lifecycle e websocket
    payments/      caixa, pagamentos e movimentacoes
    printers/      impressoras, print jobs e templates
    reports/       dashboard e relatorios
    restaurants/   restaurantes, filiais, mesas e comandas
    stock/         locais e movimentacoes de estoque
  config/          settings por ambiente, urls, asgi, celery
  tests/           exemplos pytest

frontend/
  src/
    components/    componentes reutilizaveis
    composables/   websocket, permissao, toast e impressao
    layouts/       Auth, App e PDV
    router/        rotas e guards
    services/      Axios e servicos por dominio
    stores/        Pinia
    views/         telas MVP
```

## Comandos de desenvolvimento

```bash
cp .env.example .env
docker compose up --build
```

Para rodar backend ASGI e frontend no mesmo terminal, com encerramento conjunto no `Ctrl+C`:

```bash
cd backend
python manage.py runservices
```

Para trocar o host ou a porta do backend:

```bash
python manage.py runservices 0.0.0.0:8001
# ou
python manage.py runservices --backend-host 0.0.0.0 --backend-port 8001
```

Para popular uma base local com dados demo:

```bash
python manage.py seed_demo --migrate
```

Isso cria a conta `starchef-demo`, restaurante, filial, mesas, cardapio, estoque, formas de pagamento, clientes, pedidos demo e o usuario `admin` com senha `admin12345`.

Se o SQLite local estiver com historico antigo/inconsistente de migrations, recrie a base local mantendo backup automatico:

```bash
python manage.py seed_demo --reset-sqlite
```

Para criar ou atualizar um usuario vinculado corretamente ao tenant:

```bash
python manage.py create_tenant_user --username gerente --email gerente@starchef.test --password gerente123 --profile-type manager --role-code manager
```

Por padrao esse comando cria superuser com `is_staff=True` e perfil `admin`. Para criar usuario comum, adicione `--profile-type waiter --no-superuser --no-staff`.

Em `DEBUG=True`, o banco usa SQLite local, e cache, Channels e Celery usam memoria local. Nesse modo o Celery executa tarefas em modo eager, sem worker/beat separados. Para aplicar migrations antes de subir:

```bash
python manage.py runservices --migrate
```

O settings do Django e escolhido automaticamente: `DJANGO_DEBUG=True` usa `config.settings.development`; `DJANGO_DEBUG=False` usa `config.settings.production`. `DJANGO_SETTINGS_MODULE` continua opcional para sobrescrever manualmente quando necessario.

Endpoints uteis:

- API: `http://localhost:8000/api/v1/`
- Swagger: `http://localhost:8000/api/schema/swagger-ui/`
- Admin Unfold: `http://localhost:8000/admin/`
- Frontend: `http://localhost:5173/login`

Ao usar `runservices` com outra porta de backend, por exemplo `python manage.py runservices 0.0.0.0:8001`, o frontend recebe automaticamente `VITE_API_BASE_URL=http://localhost:8001/api/v1`.

## Roadmap

MVP:

- autenticacao JWT, restaurante/filial, usuarios e permissoes;
- mesas/comandas, cardapio, abertura de pedidos e envio para cozinha;
- KDS em tempo real, fechamento de conta, pagamentos, caixa e recibo;
- dashboard inicial, auditoria basica e OpenAPI.

Versao 2:

- estoque com ficha tecnica completa, delivery completo, relatorios avancados;
- impressora termica ESC/POS, promocoes, combos e controle de entregadores.

Versao 3:

- NFC-e/NF-e, gateways de pagamento, WhatsApp, iFood/marketplaces;
- PWA offline parcial e SaaS multi-restaurante com cobranca por plano.
