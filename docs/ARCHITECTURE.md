# StarChef Architecture

## Camadas

- `backend/config`: settings por ambiente, ASGI/WSGI, Celery, URLs e OpenAPI.
- `backend/apps/core`: UUID base, timestamps, soft delete, auditoria, permissao por tenant, paginacao e erros padronizados.
- `backend/apps/*`: cada dominio possui models, serializers, viewsets, admin e services quando ha regra transacional.
- `frontend/src/services`: consumo REST via Axios com refresh token automatico.
- `frontend/src/stores`: estado global Pinia por contexto operacional.
- `frontend/src/composables`: WebSocket, permissao, toast e impressao.

## Ambientes

- `DJANGO_DEBUG=True`: seleciona automaticamente `config.settings.development`, usa SQLite local e usa memoria local para cache, Channels e Celery. Nesse modo, Celery roda em `task_always_eager`, sem depender de Redis.
- `DJANGO_DEBUG=False`: seleciona automaticamente `config.settings.production`, usa PostgreSQL e usa Redis para cache, Channels e broker/result backend do Celery.
- `config.settings.test`: mantem `DEBUG=False`, usa SQLite e memoria local para evitar dependencias externas nos testes.
- `DJANGO_SETTINGS_MODULE`: continua opcional para sobrescrever manualmente o settings quando necessario.
- `python manage.py runservices`: sobe backend ASGI e frontend em um terminal; em producao-like, tambem sobe Celery worker/beat. `Ctrl+C` encerra todos os processos filhos.
## Regras implementadas no backend

- dados filtrados por restaurante/filial em ViewSets com `TenantQuerySetMixin`;
- pedidos pagos, cancelados ou estornados ficam bloqueados para alteracao;
- cancelamento de pedido ou item exige motivo;
- item pronto exige perfil de gerente/dono/admin para retroceder;
- mesa ocupada nao abre novo pedido paralelo;
- fechamento e pagamento usam `transaction.atomic`;
- pagamento aceita chave de idempotencia;
- caixa aberto e exigido quando configurado na filial;
- baixa de estoque ocorre no pagamento ou envio para cozinha, conforme filial;
- impressoes geram `PrintJob` e `AuditLog`;
- fiscal real fica fora do MVP, com contrato futuro em `integrations.providers.FiscalProvider`.

## WebSocket KDS

- rota: `/ws/kitchen/<branch_id>/<sector>/?token=<jwt>`;
- grupos: `kitchen_branch_{branch_id}_sector_{sector}`;
- o consumer valida JWT e bloqueia filial diferente;
- `send_order_to_kitchen` emite `order_item.sent`;
- `update_order_item_status` emite `order_item.status_changed`;
- o frontend reconecta automaticamente e atualiza `kitchenStore`.

## Impressao

MVP:

- backend registra `PrintJob`;
- templates HTML em `apps/printers/templates/printers`;
- frontend usa `usePrint().printHtml(html)` com `window.print()`.

Evolucao:

- driver ESC/POS por `Printer.driver_type`;
- fila Celery para impressao automatica por setor;
- status de falha/reimpressao com permissao.

## Testes sugeridos

- unitarios: services de pedido, pagamento, caixa e estoque;
- API: filtros por filial, permissoes por endpoint, idempotencia;
- WebSocket: conexao JWT, isolamento por filial e recebimento de evento;
- frontend: stores e services com mocks;
- E2E: login, abertura de pedido, KDS e fechamento de conta.

## Pipeline CI/CD sugerido

```text
backend:
  pip install -r backend/requirements/development.txt
  python backend/manage.py makemigrations --check --dry-run
  pytest backend
  ruff check backend

frontend:
  npm ci --prefix frontend
  npm run lint --prefix frontend
  npm run build --prefix frontend

containers:
  docker compose build

deploy:
  aplicar migrations
  subir backend ASGI, workers e beat
  publicar frontend estatico (container `serve`, sem Nginx)
  validar /health/ e smoke tests
```

## Deploy

Homologacao:

- Docker Compose com PostgreSQL e Redis gerenciados pelo proprio stack;
- variaveis em `.env`;
- backups agendados com Celery Beat ou job externo.

Producao:

- PostgreSQL gerenciado com backup PITR;
- Redis gerenciado ou dedicado;
- proxy reverso HTTP/WS externo ao Compose (nginx do host, Caddy, LB da nuvem etc. — ver `infra/reverse-proxy.example.conf`);
- Django rodando em ASGI com Daphne/Uvicorn;
- Celery worker e beat separados;
- Sentry ou equivalente para erros;
- logs JSON enviados para agregador.
