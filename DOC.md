# StarChef — Documentação Técnica

> Última atualização: 2026-06-18  
> Revisão do modelo de pedidos: conta aberta, rodadas de cozinha, pagamento parcial

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Tecnologias](#3-tecnologias)
4. [Estrutura de Pastas](#4-estrutura-de-pastas)
5. [Multi-Tenancy](#5-multi-tenancy)
6. [Modelos de Dados](#6-modelos-de-dados)
7. [Endpoints da API](#7-endpoints-da-api)
8. [Frontend — Páginas e Rotas](#8-frontend--páginas-e-rotas)
9. [Fluxo Operacional](#9-fluxo-operacional)
10. [Autenticação e Permissões](#10-autenticação-e-permissões)
11. [Configurações do Ambiente](#11-configurações-do-ambiente)
12. [Rodando o Projeto](#12-rodando-o-projeto)
13. [Roadmap](#13-roadmap)

---

## 1. Visão Geral

**StarChef** é um SaaS de gestão operacional de restaurantes. Suporta múltiplos tipos de estabelecimento (restaurante, lanchonete, pizzaria, hamburgeria, dark kitchen) e múltiplos modelos de operação em paralelo: salão com mesas, balcão, delivery e retirada.

**Objetivos do MVP:**
- Abertura e fechamento de pedidos (mesa, comanda, balcão, delivery, retirada)
- KDS (Kitchen Display System) em tempo real para a cozinha
- Gestão de cardápio com ficha técnica e controle de custo
- Caixa e registro de pagamentos
- Recibo simples (não-fiscal)
- Dashboard operacional
- Multi-tenancy: uma instância atende múltiplas contas/restaurantes

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND (Vue 3)                  │
│         SPA servida via Nginx / Vite dev server      │
└────────────────────────┬────────────────────────────┘
                         │ HTTP REST + WebSocket
┌────────────────────────▼────────────────────────────┐
│              BACKEND (Django 5 + DRF)                │
│                  ASGI via Daphne                      │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │  REST API  │  │  WS Channels │  │  Celery      │  │
│  │  /api/v1/  │  │  /ws/kitchen │  │  Workers     │  │
│  └────────────┘  └──────────────┘  └─────────────┘  │
└──────┬────────────────────┬─────────────────────────┘
       │                    │
┌──────▼──────┐    ┌────────▼────────┐
│ PostgreSQL  │    │     Redis        │
│  (dados)    │    │  cache / broker  │
│             │    │  channel layer   │
└─────────────┘    └─────────────────┘
```

**Componentes:**
| Componente | Papel |
|---|---|
| Vue 3 SPA | Interface do operador (PDV, KDS, gestão) |
| Django REST Framework | API principal (CRUD, relatórios) |
| Django Channels + Daphne | WebSocket para KDS em tempo real |
| Celery | Tarefas assíncronas (impressão, cálculos, agendamentos) |
| Celery Beat | Agendamentos periódicos |
| PostgreSQL | Banco de dados principal |
| Redis | Cache, channel layer do Channels, broker do Celery |
| Nginx | Serve o frontend estático em produção |

---

## 3. Tecnologias

### Backend (Python)

| Pacote | Versão | Função |
|---|---|---|
| Django | 5.0.x | Framework web |
| djangorestframework | 3.15.x | API REST |
| djangorestframework-simplejwt | 5.3.x | Autenticação JWT |
| django-cors-headers | 4.3.x | CORS |
| django-filter | 24.1.x | Filtros na API |
| drf-spectacular | 0.27.x | Documentação OpenAPI / Swagger |
| django-channels | 4.1.x | WebSocket (KDS tempo real) |
| channels-redis | 4.2.x | Channel layer via Redis |
| daphne | 4.1.x | Servidor ASGI |
| celery | 5.4.x | Fila de tarefas assíncronas |
| redis | 5.0.x | Cache e broker |
| psycopg | 3.1.x | Driver PostgreSQL |
| python-decouple | 3.8.x | Config via variáveis de ambiente |
| Pillow | 10.0.x | Processamento de imagens |
| django-unfold | 0.43.x | Admin moderno |
| sentry-sdk | 2.5.x | Error tracking (produção) |
| gunicorn | 22.0.x | Servidor WSGI (produção alternativo) |
| pytest + pytest-django | 8.2.x / 4.8.x | Testes |
| factory-boy | 3.3.x | Fixtures de teste |
| ruff | 0.5.x | Linter |

### Frontend (JavaScript / Vue)

| Pacote | Versão | Função |
|---|---|---|
| Vue | 3.4.29 | Framework reativo |
| vue-router | 4.3.3 | Roteamento SPA |
| Pinia | 2.1.7 | State management |
| PrimeVue | 3.53.1 | Biblioteca de componentes UI |
| primeicons | 7.0.0 | Ícones (PrimeFaces) |
| Axios | 1.7.2 | HTTP client |
| xlsx | 0.18.5 | Exportação para Excel |
| Vite | 5.3.1 | Build tool e dev server |
| ESLint + eslint-plugin-vue | 9.5.0 | Linting |

**Tema UI:** `aura-light-teal` (PrimeVue built-in) com tokens CSS customizados em `styles/tokens/` e overrides em `styles/primevue-tokens.css`.

---

## 4. Estrutura de Pastas

```
starchef/
├── backend/
│   ├── apps/
│   │   ├── accounts/       # Auth, planos, usuários, roles
│   │   ├── core/           # Base models, tenancy, auditoria
│   │   ├── restaurants/    # Restaurantes, filiais, mesas, comandas
│   │   ├── menu/           # Cardápio, produtos, ingredientes, receitas
│   │   ├── orders/         # Pedidos e itens
│   │   ├── customers/      # Clientes e endereços
│   │   ├── payments/       # Caixa, pagamentos, formas de pagamento
│   │   ├── stock/          # Estoque e movimentações
│   │   ├── kitchen/        # KDS (views + consumers WebSocket)
│   │   ├── invoices/       # Notas fiscais / recibos
│   │   ├── printers/       # Impressoras e jobs de impressão
│   │   ├── reports/        # Dashboard e relatórios
│   │   └── integrations/   # Providers externos (iFood, gateways - futuro)
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py     # Configurações comuns
│   │   │   ├── dev.py      # Overrides de desenvolvimento
│   │   │   └── prod.py     # Overrides de produção
│   │   ├── urls.py         # URL root
│   │   ├── asgi.py         # Entrada ASGI (HTTP + WS)
│   │   └── wsgi.py         # Entrada WSGI (alternativo)
│   └── tests/              # Testes de integração
│
└── frontend/
    └── src/
        ├── assets/         # Logos, imagens estáticas
        ├── components/     # Componentes reutilizáveis (AppIcon, etc)
        ├── layout/         # AppLayout, Sidebar, Topbar
        ├── router/         # Definição de rotas
        ├── services/       # api.js (Axios), WebSocket composables
        ├── stores/         # Stores Pinia (auth, etc)
        ├── styles/         # Tokens CSS, overrides PrimeVue
        └── views/          # Páginas (Dashboard, PDV, KDS, ResourceListView, etc)
```

---

## 5. Multi-Tenancy

O sistema usa isolamento por **Account** (um tenant = uma conta empresarial). Toda query é automaticamente filtrada.

### Hierarquia

```
Account (tenant raiz)
└── Restaurant (marca: ex: "Pizzaria Napoli")
    └── Branch (filial: ex: "Zona Norte", "Zona Sul")
        └── Dados operacionais (mesas, pedidos, estoque...)
```

### Modelos Base

| Modelo | Herança | Escopo |
|---|---|---|
| `TenantBaseModel` | TimeStampedModel + AuditUserModel | Filtrado por `account` |
| `TenantModel` | TenantBaseModel | Filtrado por `account` + `restaurant` + `branch` |

### TenantManager

O `TenantManager` sobrescreve o `get_queryset()` e aplica automaticamente filtros `account`, `restaurant` e `branch` com base no usuário autenticado (via `request` injetado pelo `TenantMiddleware`).

### Soft Delete

Todos os `TenantBaseModel` possuem `deleted_at`. Registros "deletados" têm `deleted_at` preenchido e são filtrados pelo manager por padrão. O histórico é preservado para auditoria.

---

## 6. Modelos de Dados

### 6.1 App `accounts`

#### `Plan`
Planos de assinatura do SaaS.

| Campo | Tipo | Descrição |
|---|---|---|
| code | CharField único | Identificador (ex: `basic`, `pro`) |
| name | CharField | Nome de exibição |
| max_branches | IntegerField | Limite de filiais |
| max_users | IntegerField | Limite de usuários |
| features | JSONField | Features habilitadas por plano |
| is_active | BooleanField | Plano disponível para contratação |

#### `Account`
Raiz do tenant — representa a empresa/conta.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Nome da conta/empresa |
| slug | SlugField único | Identificador na URL |
| document | CharField | CNPJ / CPF |
| email | EmailField | E-mail principal |
| phone | CharField | Telefone |
| status | CharField | `active` / `suspended` / `canceled` |
| plan | ForeignKey → Plan | Plano contratado |
| timezone | CharField | Timezone padrão (ex: `America/Sao_Paulo`) |
| default_currency | CharField | Moeda padrão (`BRL`) |
| trial_ends_at | DateTimeField | Fim do trial |
| subscription_status | CharField | `trial` / `active` / `past_due` / `canceled` |
| is_active | BooleanField | Conta ativa |

#### `Subscription`
Controle do período de faturamento.

| Campo | Tipo | Descrição |
|---|---|---|
| account | OneToOneField → Account | Conta associada |
| plan | ForeignKey → Plan | Plano vigente |
| status | CharField | Status atual |
| current_period_starts_at | DateTimeField | Início do período |
| current_period_ends_at | DateTimeField | Fim do período |
| metadata | JSONField | Dados do gateway de pagamento |

#### `Permission`
Permissões granulares do sistema.

| Campo | Tipo | Descrição |
|---|---|---|
| code | CharField único | Ex: `order.create`, `payment.refund` |
| name | CharField | Nome legível |
| description | TextField | Descrição da permissão |

#### `Role` (TenantBaseModel)
Papéis de usuário por restaurant.

| Campo | Tipo | Descrição |
|---|---|---|
| code | CharField | Ex: `waiter`, `manager` |
| name | CharField | Nome de exibição |
| restaurant | ForeignKey → Restaurant (null) | Escopo do papel |
| permissions | ManyToManyField → Permission | Permissões do papel |
| max_discount_percent | DecimalField | Desconto máximo que pode aplicar |
| is_system | BooleanField | Papel padrão do sistema (não editável) |
| is_active | BooleanField | — |

#### `UserProfile` (TenantBaseModel)
Vincula um `User` Django a um perfil operacional.

| Campo | Tipo | Descrição |
|---|---|---|
| user | OneToOneField → User | Usuário Django |
| phone | CharField | Telefone |
| profile_type | CharField | `admin` / `owner` / `manager` / `waiter` / `kitchen` / `cashier` / `driver` |
| role | ForeignKey → Role | Papel atribuído |
| restaurant | ForeignKey → Restaurant | Restaurante do perfil |
| branch | ForeignKey → Branch (null) | Filial específica (null = acesso a todas) |
| specific_permissions | ManyToManyField → Permission | Permissões adicionais além do role |
| last_login_at | DateTimeField | — |
| is_active | BooleanField | — |

---

### 6.2 App `core`

Modelos abstratos que servem de base para todos os outros apps.

| Modelo | Abstract | Campos adicionados |
|---|---|---|
| `UUIDModel` | Sim | `id` (UUID, PK automático) |
| `TimeStampedModel` | Sim | `created_at`, `updated_at` |
| `AuditUserModel` | Sim | `created_by`, `updated_by` (FK User) |
| `TenantBaseModel` | Não | `account` (FK), `deleted_at` (soft delete) |
| `TenantModel` | Não | herda TenantBaseModel + `restaurant`, `branch` |

#### `AuditLog` (TenantBaseModel)
Registro imutável de toda ação relevante do sistema.

| Campo | Tipo | Descrição |
|---|---|---|
| actor | ForeignKey → User | Quem executou |
| restaurant / branch | FK | Contexto |
| action | CharField | `created` / `updated` / `deleted` / `cancelled` / `payment` / `printed` |
| entity | CharField | Nome do modelo (ex: `Order`) |
| object_id | UUIDField | ID do objeto afetado |
| reason | CharField | Motivo (opcional) |
| changes | JSONField | Diff antes/depois |
| metadata | JSONField | Dados extras |
| ip_address | GenericIPAddressField | IP do operador |

---

### 6.3 App `restaurants`

#### `Restaurant` (TenantBaseModel)
Representa uma marca/empresa (ex: "Pizzaria Napoli").

| Campo | Tipo | Descrição |
|---|---|---|
| legal_name | CharField | Razão social |
| trade_name | CharField | Nome fantasia |
| cnpj | CharField único | — |
| state_registration | CharField | Inscrição estadual |
| phone / email | — | Contato |
| address, city, state, zip_code | — | Endereço |
| logo | ImageField | Logotipo |
| default_service_fee_percent | DecimalField | Taxa de serviço padrão |
| operational_settings | JSONField | Config operacional (horários, etc) |
| fiscal_settings | JSONField | Config fiscal (regime tributário, etc) |
| print_settings | JSONField | Config de impressão padrão |
| is_active | BooleanField | — |

#### `Branch` (TenantBaseModel)
Filial de um restaurante (ex: "Zona Norte").

| Campo | Tipo | Descrição |
|---|---|---|
| restaurant | ForeignKey → Restaurant | — |
| name | CharField | Nome da filial |
| cnpj / phone / email / address... | — | Dados próprios da filial |
| opening_hours | JSONField | Horários de funcionamento por dia |
| default_service_fee_percent | DecimalField | Pode sobrescrever o restaurante |
| require_open_cash_register | BooleanField | Exige caixa aberto para aceitar pedidos |
| stock_deduction_timing | CharField | `payment` ou `kitchen` |
| print_settings / fiscal_settings | JSONField | Config própria da filial |

#### `TableSector` (TenantModel)
Setores dentro de uma filial (ex: Salão, Varanda).

| Campo | Tipo |
|---|---|
| name | CharField |
| display_order | IntegerField |
| is_active | BooleanField |

#### `Table` (TenantModel)
Mesa com status operacional em tempo real.

| Campo | Tipo | Descrição |
|---|---|---|
| sector | ForeignKey → TableSector | — |
| number | CharField | Identificador visível (ex: "12", "A3") |
| capacity | IntegerField | Número de lugares |
| status | CharField | `free` / `occupied` / `reserved` / `cleaning` |
| current_order_id | UUIDField (null) | Pedido aberto na mesa |
| joined_to | ForeignKey → self (null) | Mesa unificada a outra |
| is_active | BooleanField | — |

#### `Command` (TenantModel)
Comanda para pedidos de balcão/retirada.

| Campo | Tipo | Descrição |
|---|---|---|
| code | CharField | Número/código da comanda |
| customer_name | CharField | Nome do cliente |
| status | CharField | `open` / `closed` |

#### `DeliveryZone` (TenantModel)
Zona de entrega com raio e taxa.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Ex: "Até 3km" |
| min_radius_km | DecimalField | Raio mínimo |
| max_radius_km | DecimalField | Raio máximo |
| delivery_fee | DecimalField | Taxa de entrega |
| estimated_minutes | IntegerField | Tempo estimado |

#### `Deliveryman` (TenantModel)
Cadastro de entregadores.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | — |
| phone | CharField | — |
| vehicle_type | CharField | `bike` / `motorcycle` / `car` / `foot` |
| vehicle_plate | CharField | Placa |

---

### 6.4 App `menu`

#### `ProductCategory` (TenantModel)
Categorias hierárquicas de produtos.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | — |
| parent | ForeignKey → self (null) | Categoria pai (hierarquia 2 níveis) |
| display_order | IntegerField | Ordem de exibição |
| is_active | BooleanField | — |

#### `Product` (TenantModel)
Item do cardápio.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | — |
| internal_code | CharField | Código interno da casa |
| description | TextField | — |
| category | ForeignKey → ProductCategory | — |
| image | ImageField | Foto do produto |
| sale_price | DecimalField | Preço de venda |
| promotional_price | DecimalField (null) | Preço promocional ativo |
| estimated_cost | DecimalField | Custo estimado (da ficha técnica) |
| margin_percent | DecimalField | Margem calculada |
| product_type | CharField | `meal` / `drink` / `dessert` / `combo` / `addon` / `input` |
| average_preparation_time | IntegerField | Minutos médios de preparo |
| production_sector | CharField | `kitchen` / `bar` / `dessert` |
| controls_stock | BooleanField | Se desconta estoque ao vender |
| allows_addons | BooleanField | Permite adicionais |
| allows_notes | BooleanField | Permite observação do cliente |
| available_for_table / counter / delivery | BooleanField | Disponibilidade por canal |
| is_active | BooleanField | — |

**Property:** `current_price` — retorna `promotional_price` se definido, senão `sale_price`.

#### `ProductVariation` (TenantModel)
Variações de um produto (ex: Tamanho, Ponto da carne).

| Campo | Tipo | Descrição |
|---|---|---|
| product | ForeignKey → Product | — |
| name | CharField | Ex: "Grande", "Mal passado" |
| price_delta | DecimalField | Acréscimo/desconto no preço |
| is_required | BooleanField | Seleção obrigatória |

#### `ProductAddon` (TenantModel)
Adicionais aplicáveis a múltiplos produtos.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Ex: "Bacon extra" |
| products | ManyToManyField → Product | Produtos que aceitam este adicional |
| price | DecimalField | Preço do adicional |
| production_sector | CharField | Setor de preparação |

#### `Ingredient` (TenantModel)
Insumos para fichas técnicas.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | — |
| unit | CharField | `unit` / `kg` / `g` / `l` / `ml` |
| average_cost | DecimalField | Custo médio por unidade |
| minimum_stock | DecimalField | Estoque mínimo para alerta |

#### `Recipe` (TenantModel)
Ficha técnica de um produto.

| Campo | Tipo | Descrição |
|---|---|---|
| product | OneToOneField → Product | — |
| yield_quantity | DecimalField | Rendimento da receita |
| total_cost | DecimalField | Custo total calculado |
| auto_deduct_stock | BooleanField | Baixa estoque automaticamente |

#### `RecipeItem` (TenantModel)
Linha de ingrediente de uma receita.

| Campo | Tipo | Descrição |
|---|---|---|
| recipe | ForeignKey → Recipe | — |
| ingredient | ForeignKey → Ingredient | — |
| quantity | DecimalField | Quantidade utilizada |
| unit | CharField | Unidade de medida |
| ingredient_cost | DecimalField | Custo unitário no momento |
| total_cost | DecimalField | Custo total desta linha |

#### `Menu` (TenantModel)
Cardápio por canal de venda.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Ex: "Cardápio Almoço" |
| slug | SlugField único | Para URL pública |
| channel | CharField | `all` / `table` / `delivery` / `counter` / `digital` |
| available_from / available_until | TimeField | Horário de disponibilidade |
| is_active | BooleanField | — |

#### `MenuItem` (TenantModel)
Produto dentro de um cardápio.

| Campo | Tipo | Descrição |
|---|---|---|
| menu | ForeignKey → Menu | — |
| product | ForeignKey → Product | — |
| display_order | IntegerField | Ordem de exibição |
| override_price | DecimalField (null) | Preço específico para este cardápio |

---

### 6.5 App `orders`

> **Conceito central:** o pedido é uma **conta aberta** (`open check`), não uma venda finalizada. A venda só existe quando o pagamento é confirmado. Pedido, produção e pagamento são três ciclos independentes.

#### Os quatro conceitos do ciclo de pedido

| Conceito | Modelo | Descrição |
|---|---|---|
| Conta aberta | `Order` | A conta do cliente — pode receber itens em várias rodadas |
| Item lançado | `OrderItem` | Cada produto adicionado à conta |
| Rodada de produção | `OrderBatch` | Grupo de itens enviados à cozinha/bar de uma vez |
| Pagamento | `Payment` | Registro financeiro — pode haver vários por pedido |

---

#### `Order` (TenantModel)
Conta aberta do cliente. Representa o ciclo completo da operação.

| Campo | Tipo | Descrição |
|---|---|---|
| sequence | IntegerField | Número sequencial por filial (ex: #1042) |
| order_type | CharField | `table` / `command` / `counter` / `delivery` / `takeaway` / `internal` |
| table | ForeignKey → Table (null) | Mesa vinculada (order_type=table) |
| command | ForeignKey → Command (null) | Comanda vinculada (order_type=command) |
| customer | ForeignKey → Customer (null) | Cliente associado |
| delivery_address | ForeignKey → CustomerAddress (null) | Endereço de entrega (order_type=delivery) |
| pickup_time | DateTimeField (null) | Horário previsto de retirada (order_type=takeaway) |
| responsible_user | ForeignKey → User | Operador que abriu |
| closed_by | ForeignKey → User (null) | Operador que fechou |
| **status** | CharField | Ciclo operacional — ver tabela abaixo |
| **production_status** | CharField | Ciclo de produção — ver tabela abaixo |
| **payment_status** | CharField | Ciclo financeiro — ver tabela abaixo |
| opened_at / closed_at | DateTimeField | Timestamps do ciclo |
| subtotal | DecimalField | Soma dos itens |
| service_fee | DecimalField | Taxa de serviço |
| discount | DecimalField | Desconto aplicado |
| delivery_fee | DecimalField | Taxa de entrega |
| total | DecimalField | Total final |
| general_notes | TextField | Observações gerais |
| change_history | JSONField | Histórico de alterações de status |
| cancel_reason | CharField | Motivo do cancelamento |

**status — ciclo operacional da conta:**
| Valor | Descrição |
|---|---|
| `open` | Conta aberta — recebe itens |
| `awaiting_payment` | Conta fechada — aguardando pagamento |
| `paid` | Pagamento concluído |
| `cancelled` | Cancelado antes de pagar |
| `refunded` | Estornado após pagamento |

**production_status — ciclo de produção:**
| Valor | Descrição |
|---|---|
| `idle` | Nenhum item enviado ainda |
| `sent_to_kitchen` | Primeira rodada enviada |
| `preparing` | Cozinha iniciou o preparo |
| `partially_ready` | Parte dos itens prontos |
| `ready` | Todos os itens prontos |
| `delivered` | Itens entregues ao cliente |

**payment_status — ciclo financeiro:**
| Valor | Descrição |
|---|---|
| `pending` | Nenhum pagamento registrado |
| `partial` | Pagamento parcial — soma dos pagamentos < total |
| `paid` | Pagamento completo — soma ≥ total |
| `refunded` | Estornado |

> **Regra:** `Order.status = paid` só pode ser definido quando `payment_status = paid`. O caixa fecha a conta, não o status de produção.
>
> **is_locked:** pedido com `status` em `paid`, `cancelled` ou `refunded` não pode receber novos itens.
>
> **Regra para comanda:** uma comanda aberta deve ter no máximo **um** pedido com `status = open`. Se o operador tentar abrir outro, o sistema recusa e oferece abrir o existente.

---

#### `OrderBatch` (TenantModel)
Rodada de produção — grupo de itens enviados à cozinha de uma vez dentro do mesmo pedido.

Inspiração: Oracle Simphony chama isso de "round" dentro de um "check". A Square chama de "tender round".

| Campo | Tipo | Descrição |
|---|---|---|
| order | ForeignKey → Order | Pedido pai |
| batch_number | IntegerField | Número sequencial da rodada (1, 2, 3...) |
| production_sector | CharField | Setor destino desta rodada (`kitchen` / `bar` / `dessert`) |
| status | CharField | `pending` / `sent` / `done` |
| sent_at | DateTimeField | Quando foi enviada |
| sent_by | ForeignKey → User | Operador que enviou |
| printed_at | DateTimeField (null) | Quando o ticket foi impresso |

**Por que registrar rodadas?**  
O restaurante precisa saber o histórico de produção: "Rodada 1 (20:10): hambúrguer + suco. Rodada 2 (20:30): sobremesa." Isso permite rastreabilidade, reimpressão de tickets e análise de tempo de preparo por rodada.

---

#### `OrderItem` (TenantModel)
Item individual de um pedido. Sempre pertence a uma rodada (`OrderBatch`).

| Campo | Tipo | Descrição |
|---|---|---|
| order | ForeignKey → Order | Conta pai |
| batch | ForeignKey → OrderBatch (null) | Rodada em que foi enviado |
| product | ForeignKey → Product | — |
| quantity | DecimalField | — |
| unit_price | DecimalField | Preço travado no momento do lançamento |
| total_price | DecimalField | quantity × unit_price |
| variations | JSONField | Variações escolhidas (snapshot) |
| customer_note | TextField | Observação do cliente |
| production_sector | CharField | Setor de preparo |
| status | CharField | `pending` / `sent` / `preparing` / `ready` / `delivered` / `cancelled` / `comped` |
| void_reason | CharField | Motivo do cancelamento/cortesia |
| launched_by | ForeignKey → User | Operador que lançou |
| launched_at | DateTimeField | — |
| sent_to_kitchen_at | DateTimeField | — |
| preparation_started_at | DateTimeField | — |
| ready_at | DateTimeField | — |
| delivered_at | DateTimeField | — |

**Status do item:**
| Valor | Quem muda | Descrição |
|---|---|---|
| `pending` | PDV | Lançado, aguardando envio |
| `sent` | PDV | Enviado para cozinha/bar |
| `preparing` | KDS | Cozinheiro iniciou o preparo |
| `ready` | KDS | Pronto para entrega |
| `delivered` | PDV / Garçom | Entregue ao cliente |
| `cancelled` | PDV (antes de sent) | Cancelado antes de preparar (void) |
| `comped` | Gerente | Cortesia após preparado (comp) |

> **Regra:** item só pode ser cancelado (`cancelled`) se `status = pending`. Se já foi enviado (`sent` ou além), o gerente deve usar `comped` para registrar cortesia sem afetar o estoque retroativamente.

---

#### `OrderItemAddon` (TenantModel)
Adicional aplicado a um item.

| Campo | Tipo | Descrição |
|---|---|---|
| item | ForeignKey → OrderItem | — |
| addon | ForeignKey → ProductAddon | — |
| quantity | DecimalField | — |
| unit_price | DecimalField | — |
| total_price | DecimalField | — |

---

### 6.6 App `customers`

#### `Customer` (TenantModel)
Cliente do restaurante.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | — |
| phone | CharField | — |
| email | EmailField | — |
| document | CharField | CPF |
| internal_notes | TextField | Anotações internas |
| is_active | BooleanField | — |

#### `CustomerAddress` (TenantModel)
Endereços de entrega cadastrados do cliente.

| Campo | Tipo | Descrição |
|---|---|---|
| customer | ForeignKey → Customer | — |
| label | CharField | Ex: "Casa", "Trabalho" |
| street, number, complement | CharField | — |
| district, city, state, zip_code | CharField | — |
| reference | TextField | Ponto de referência |
| is_default | BooleanField | Endereço padrão |

---

### 6.7 App `payments`

#### `PaymentMethod` (TenantModel)
Forma de pagamento cadastrada por filial.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Ex: "Dinheiro", "Pix", "Cartão Débito" |
| method_type | CharField | `cash` / `card` / `pix` / `voucher` / `other` |
| requires_reference | BooleanField | Exige número de referência (ex: número aprovação) |
| is_active | BooleanField | — |

#### `Payment` (TenantModel)
Registro de cada pagamento efetuado.

| Campo | Tipo | Descrição |
|---|---|---|
| order | ForeignKey → Order | — |
| payment_method | ForeignKey → PaymentMethod | — |
| amount | DecimalField | Valor pago |
| change_amount | DecimalField | Troco |
| status | CharField | `pending` / `approved` / `cancelled` / `refunded` |
| idempotency_key | CharField | Previne pagamentos duplicados |
| metadata | JSONField | Dados adicionais (referência, autorização) |
| paid_at | DateTimeField | — |

#### `CashRegister` (TenantModel)
Caixa de uma filial em um turno.

| Campo | Tipo | Descrição |
|---|---|---|
| opened_by | ForeignKey → User | Operador que abriu |
| closed_by | ForeignKey → User (null) | Operador que fechou |
| status | CharField | `open` / `closed` |
| opened_at / closed_at | DateTimeField | — |
| opening_amount | DecimalField | Fundo de caixa inicial |
| expected_amount | DecimalField | Total esperado (calculado) |
| actual_amount | DecimalField | Total informado no fechamento |
| difference_amount | DecimalField | Diferença (sobra/falta) |
| notes | TextField | Observações do fechamento |

#### `CashMovement` (TenantModel)
Movimentação individual do caixa.

| Campo | Tipo | Descrição |
|---|---|---|
| cash_register | ForeignKey → CashRegister | — |
| payment | ForeignKey → Payment (null) | Pagamento relacionado (se venda) |
| operator | ForeignKey → User | — |
| movement_type | CharField | `opening` / `sale` / `withdrawal` / `supply` / `closing` / `adjustment` |
| amount | DecimalField | — |
| reason | CharField | — |
| metadata | JSONField | — |

---

### 6.8 App `stock`

#### `StockLocation` (TenantModel)
Locais físicos de armazenamento.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Ex: "Câmara fria", "Seco", "Bar" |
| description | TextField | — |
| is_active | BooleanField | — |

#### `StockMovement` (TenantModel)
Cada entrada ou saída de ingrediente no estoque.

| Campo | Tipo | Descrição |
|---|---|---|
| ingredient | ForeignKey → Ingredient | — |
| location | ForeignKey → StockLocation | — |
| order_item | ForeignKey → OrderItem (null) | Baixa automática por venda |
| operator | ForeignKey → User | — |
| movement_type | CharField | `in` / `out` / `adjustment` / `sale` / `inventory` |
| quantity | DecimalField | — |
| unit_cost | DecimalField | Custo unitário desta movimentação |
| total_cost | DecimalField | — |
| reason | CharField | Justificativa (ex: "Compra NF 1234") |

---

### 6.9 App `invoices`

#### `Invoice` (TenantModel)
Documento fiscal associado a um pedido.

| Campo | Tipo | Descrição |
|---|---|---|
| order | OneToOneField → Order | — |
| phase | CharField | `receipt` (recibo simples) / `fiscal` (NFe futura) |
| status | CharField | `draft` / `issued` / `cancelled` / `error` |
| number | CharField | Número do documento |
| provider | CharField | Provedor fiscal |
| fiscal_payload | JSONField | Dados enviados ao provedor |
| xml_content | TextField | XML da nota (quando NFe) |
| danfe_url | URLField | URL do DANFE |
| error_message | TextField | Erro do provedor |
| issued_at | DateTimeField | — |

---

### 6.10 App `printers`

#### `Printer` (TenantModel)
Impressora cadastrada.

| Campo | Tipo | Descrição |
|---|---|---|
| name | CharField | Ex: "Cozinha", "Balcão", "Caixa" |
| sector | CharField | Setor de destino |
| driver_type | CharField | `browser` (impressão via JS) / `escpos` (térmica) |
| endpoint | CharField | URL/IP da impressora (driver escpos) |
| auto_print | BooleanField | Imprime automaticamente ao receber job |
| settings | JSONField | Configurações de papel, colunas, etc |

#### `PrintJob` (TenantModel)
Job de impressão — fila e histórico.

| Campo | Tipo | Descrição |
|---|---|---|
| printer | ForeignKey → Printer (null) | Impressora de destino |
| order | ForeignKey → Order (null) | Pedido relacionado |
| job_type | CharField | `kitchen_ticket` / `bar_ticket` / `table_bill` / `receipt` / `payment_receipt` / `cash_close` |
| status | CharField | `pending` / `rendered` / `printed` / `failed` |
| payload | JSONField | Dados para renderização |
| html_content | TextField | HTML renderizado |
| error_message | TextField | Erro de impressão |
| printed_by | ForeignKey → User | — |
| printed_at | DateTimeField | — |

---

## 7. Endpoints da API

**Base URL:** `/api/v1/`

### Autenticação
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/auth/login/` | Obter access + refresh token |
| POST | `/auth/refresh/` | Renovar access token |
| POST | `/auth/verify/` | Verificar validade do token |
| GET | `/auth/me/` | Dados do usuário autenticado |
| POST | `/auth/logout/` | Blacklist do refresh token |

### Contas e Planos
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/accounts/` | Contas/tenants |
| GET/POST | `/plans/` | Planos de assinatura |
| GET/POST | `/subscriptions/` | Assinaturas |
| GET/POST | `/system-config/` | Configurações globais |

### Usuários e Permissões
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/users/` | Usuários |
| GET/POST | `/roles/` | Papéis de acesso |

### Estrutura
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/restaurants/` | Restaurantes |
| GET/POST | `/branches/` | Filiais |
| GET/POST | `/tables/sectors/` | Setores de mesa |
| GET/POST/PATCH | `/tables/` | Mesas |
| GET/POST | `/delivery/zones/` | Zonas de entrega |
| GET/POST | `/delivery/deliverymen/` | Entregadores |

### Clientes
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/customers/` | Clientes |
| GET/POST | `/customers/addresses/` | Endereços |

### Cardápio
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/menu/categories/` | Categorias |
| GET/POST | `/menu/products/` | Produtos |
| GET/POST | `/menu/addons/` | Adicionais |
| GET/POST | `/menu/variations/` | Variações |
| GET/POST | `/menu/ingredients/` | Ingredientes |
| GET/POST | `/menu/recipes/` | Receitas |
| GET/POST | `/menu/recipe-items/` | Itens de receita |
| GET/POST | `/menu/menus/` | Cardápios |
| GET/POST | `/menu/menu-items/` | Itens de cardápio |
| GET | `/public/menu/<slug>/` | Cardápio público (sem autenticação) |

### Pedidos
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/orders/` | Listar e criar pedidos |
| GET/PATCH | `/orders/{id}/` | Detalhar e atualizar pedido |
| POST | `/orders/{id}/items/` | Adicionar item (status=pending) |
| DELETE | `/orders/{id}/items/{item_id}/` | Cancelar item pending (void) |
| POST | `/orders/{id}/items/{item_id}/comp/` | Cortesia em item ja produzido (comp) |
| POST | `/orders/{id}/send-to-kitchen/` | Criar rodada com itens pending |
| GET | `/orders/{id}/batches/` | Listar rodadas do pedido |
| POST | `/orders/{id}/close/` | Fechar conta (gera total, status=awaiting_payment) |
| POST | `/orders/{id}/pay/` | Registrar pagamento (aceita parcial) |
| GET | `/orders/{id}/payments/` | Listar pagamentos do pedido |
| POST | `/orders/{id}/cancel/` | Cancelar pedido (requer motivo) |
| POST | `/orders/{id}/refund/` | Estornar pedido pago |
| POST | `/orders/{id}/transfer/` | Transferir pedido para outro operador |

### KDS (Cozinha)
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/kitchen/orders/` | Pedidos em preparo (read-only) |
| GET | `/kitchen/items/` | Itens por setor de produção |
| POST | `/kitchen/items/{id}/status/` | Avançar status do item |

**WebSocket:** `ws://<host>/ws/kitchen/<branch_id>/<sector>/`
Eventos: `item_status_changed`, `new_order`, `order_updated`

### Pagamentos e Caixa
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/payments/methods/` | Formas de pagamento |
| GET | `/payments/` | Histórico de pagamentos |
| GET/POST | `/cash-register/` | Caixas |
| POST | `/cash-register/open/` | Abrir caixa |
| POST | `/cash-register/{id}/close/` | Fechar caixa |

### Estoque
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/stock/locations/` | Locais de estoque |
| GET/POST | `/stock/movements/` | Movimentações |
| GET | `/stock/alerts/` | Ingredientes abaixo do mínimo |

### Documentos Fiscais e Impressão
| Método | Endpoint | Descrição |
|---|---|---|
| GET/POST | `/invoices/` | Notas fiscais / recibos |
| GET/POST | `/printers/` | Impressoras |
| GET/POST | `/print-jobs/` | Jobs de impressão |

### Relatórios
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/reports/dashboard/` | KPIs do dia / semana / mês |
| GET | `/reports/sales/` | Relatório de vendas (exportável) |

---

## 8. Frontend — Páginas e Rotas

### Layout

O app usa dois layouts:
- **`AppLayout`** — com Sidebar + Topbar, para todas as páginas autenticadas
- **`AuthLayout`** — sem sidebar, para Login

### Páginas

| Rota | Componente | Descrição |
|---|---|---|
| `/login` | `LoginScreen` | Autenticação com JWT |
| `/` | `DashboardView` | KPIs do dia, pedidos em aberto, alertas |
| `/pdv` | `PdvView` | PDV — criação de pedidos, adição de itens, pagamento |
| `/kds` | `KdsView` | Cozinha — itens em 3 colunas (Novos / Em preparo / Prontos) |
| `/reports` | `ReportsView` | Relatórios de vendas e operação |

### Páginas Genéricas (ResourceListView + ResourceFormView)

O sistema usa dois componentes genéricos que atendem a todos os CRUDs via props:

**`ResourceListView`** — tabela com busca, filtros, paginação, sidebar de detalhe  
**`ResourceFormView`** — formulário de criação/edição com validação

| Rota | Recurso | Endpoint | Global? |
|---|---|---|---|
| `/pedidos` | Pedidos | `/orders/` | — |
| `/mesas` | Mesas | `/tables/` | — |
| `/clientes` | Clientes | `/customers/` | — |
| `/caixa` | Caixa | `/cash-register/` | — |
| `/cardapio` | Produtos | `/menu/products/` | — |
| `/categorias` | Categorias | `/menu/categories/` | — |
| `/ingredientes` | Ingredientes | `/menu/ingredients/` | — |
| `/receitas` | Receitas | `/menu/recipes/` | — |
| `/cardapios` | Cardápios | `/menu/menus/` | — |
| `/adicionais` | Adicionais | `/menu/addons/` | — |
| `/estoque` | Movimentações | `/stock/movements/` | — |
| `/locais-estoque` | Locais | `/stock/locations/` | — |
| `/zonas-entrega` | Zonas | `/delivery/zones/` | — |
| `/entregadores` | Entregadores | `/delivery/deliverymen/` | — |
| `/formas-pagamento` | Formas Pgto | `/payments/methods/` | ✓ |
| `/pagamentos` | Pagamentos | `/payments/` | ✓ |
| `/notas-fiscais` | NF / Recibos | `/invoices/` | ✓ |
| `/impressoras` | Impressoras | `/printers/` | ✓ |
| `/restaurantes` | Restaurantes | `/restaurants/` | ✓ |
| `/filiais` | Filiais | `/branches/` | ✓ |
| `/usuarios` | Usuários | `/users/` | ✓ |
| `/perfis` | Perfis/Roles | `/roles/` | ✓ |

> **Global?** — Rotas marcadas com ✓ ignoram o filtro de restaurant/branch e exibem todos os dados da conta, independente do escopo selecionado na sidebar.

### Topbar

- **Novo pedido** — botão primário, navega para `/pdv`. Visível para: admin, owner, manager, waiter, cashier.
- **Tema** — alterna dark/light mode
- **Notificações** — badge de pedidos abertos
- **Usuário** — menu com nome, filial ativa, logout

### Sidebar

Organizada em grupos por função. Itens condicionais por `profile_type`:

- **Principal:** Painel, Pedidos (badge), KDS (badge)
- **Operação:** Mesas, Caixa (cashier+), Clientes
- **Cardápio:** Produtos, Categorias, Adicionais, Ingredientes, Receitas, Cardápios
- **Delivery:** Zonas de entrega, Entregadores
- **Financeiro:** Estoque, Locais de estoque, Formas de pagamento, Pagamentos, Notas fiscais
- **Gestão:** Relatórios, Restaurantes, Filiais, Usuários, Perfis, Impressoras

### Seletor de Escopo (Sidebar)

Administradores (`admin`, `is_superuser`) podem selecionar entre "Todos os restaurantes" ou um restaurante específico. A seleção persiste em `localStorage` e propaga o parâmetro `?restaurant=<id>` em todas as chamadas de API.

---

## 9. Fluxo Operacional

> **Princípio fundamental:** o pedido é uma conta aberta (*open check*). A venda só existe quando o pagamento é confirmado. Itens podem ser adicionados em várias rodadas antes do fechamento. Não crie um pedido novo para cada rodada de consumo — adicione itens ao pedido existente.

---

### 9.1 Os três ciclos independentes de um pedido

```
CICLO DA CONTA (Order.status)
  open → awaiting_payment → paid
                          ↘ cancelled / refunded

CICLO DE PRODUCAO (Order.production_status)
  idle → sent_to_kitchen → preparing → partially_ready → ready → delivered

CICLO FINANCEIRO (Order.payment_status)
  pending → partial → paid
                    ↘ refunded
```

Um pedido pode estar `payment_status = partial` (cliente pagou parte) enquanto ainda `status = open` (conta não foi fechada). Isso é normal em restaurantes onde o cliente pode adiantar um pagamento.

---

### 9.2 Fluxo por tipo de operacao

#### Mesa

```
Cliente senta na Mesa 05
→ Operador abre pedido (order_type=table, table=Mesa05)
→ Mesa.status = occupied
→ Lanca itens (OrderItem.status = pending)
→ Envia para cozinha → OrderBatch criada (#1) → KDS notificado
→ Cliente pede mais → novos itens (pending)
→ Envia novamente → OrderBatch #2 → KDS notificado
→ Tudo entregue → Operador fecha conta
→ Order.status = awaiting_payment
→ Calcula: subtotal + taxa de servico - desconto = total
→ Registra pagamento(s)
→ Order.status = paid | payment_status = paid
→ Mesa.status = cleaning (ou free)
```

#### Comanda

```
Cliente recebe Comanda 032
→ Operador abre pedido (order_type=command, command=032)
→ Command.status = open
→ Lanca itens → envia → KDS
→ Cliente pede mais → novos itens no MESMO pedido → nova rodada
→ No caixa: busca "Comanda 032"
→ Sistema localiza o pedido aberto vinculado
→ Fecha conta → registra pagamento
→ Command.status = closed
```

> **Regra:** uma comanda aberta so pode ter **um** pedido com `status = open`. Se o operador tentar abrir outro pedido para a mesma comanda, o sistema deve bloquear e perguntar: "Ja existe um pedido aberto para esta comanda. Deseja abri-lo?"

#### Balcao / Fast-food

```
Cliente faz pedido no balcao
→ Operador lanca itens
→ Total calculado instantaneamente
→ Cliente paga ANTES do preparo
→ Order.payment_status = paid (antes de ir para cozinha)
→ Pedido vai para cozinha/bar
→ Cliente recebe senha
→ Order.production_status = preparing → ready
→ Cliente retira → Order.production_status = delivered
→ Order.status = paid
```

> Neste modelo, `payment_status = paid` e `production_status = preparing` coexistem. Por isso os dois ciclos sao separados.

#### Retirada (Takeaway)

```
Cliente solicita retirada (presencial ou por telefone)
→ Operador cria pedido (order_type=takeaway)
→ Registra nome, telefone, horario previsto (pickup_time)
→ Pode pagar agora ou na retirada
→ Pedido vai para cozinha
→ Fica pronto
→ Cliente retira
→ Se nao pagou: registra pagamento agora
→ Order.status = paid
```

#### Delivery

```
Cliente faz pedido (presencial, telefone ou integração futura)
→ Operador cria pedido (order_type=delivery)
→ Vincula cliente + endereco de entrega
→ Calcula taxa de entrega pela zona
→ Define payment_timing: pay_now / pay_on_delivery
→ Pedido para cozinha
→ Pronto → atribui entregador
→ Saiu para entrega
→ Entregue → registra pagamento (se pay_on_delivery)
→ Order.status = paid
```

---

### 9.3 Rodadas de producao (OrderBatch)

Cada clique em "Enviar para cozinha" cria uma nova rodada (`OrderBatch`). Somente os itens com `status = pending` sao incluidos na rodada.

```
Pedido #1001 — Comanda 032

Rodada 1 (20:10) — OrderBatch #1
  Item: X-Burger    status: preparing → ready → delivered
  Item: Coca-Cola   status: preparing → ready → delivered

[cliente pede mais]

Rodada 2 (20:45) — OrderBatch #2
  Item: Batata frita  status: sent → preparing → ready
  Item: Suco          status: sent → preparing
```

**Endpoint:** `POST /orders/{id}/send-to-kitchen/`
- Busca todos os `OrderItem` com `status = pending` do pedido
- Cria um `OrderBatch` com `batch_number` sequencial
- Muda os itens para `status = sent`
- Notifica o KDS via WebSocket com os itens da nova rodada

---

### 9.4 Ciclo de status do item no KDS

```
pending  →  sent  →  preparing  →  ready  →  delivered
                                           ↘ comped (cortesia apos preparo)
          ↘ cancelled (somente antes de sent)
```

| Transicao | Quem executa | Como |
|---|---|---|
| `pending → sent` | PDV | Clicar "Enviar para cozinha" |
| `sent → preparing` | KDS | Clicar "Iniciar preparo" |
| `preparing → ready` | KDS | Clicar "Marcar pronto" |
| `ready → delivered` | PDV / Garcom | Confirmar entrega |
| `pending → cancelled` | PDV | Cancelar antes de enviar (void) |
| `* → comped` | Gerente | Cortesia apos producao iniciada |

---

### 9.5 Pagamento parcial e divisao de conta

Um pedido pode receber **multiplos pagamentos**. O `payment_status` e calculado automaticamente:

```
Mesa 10 — Total: R$ 300,00

Payment #1: Pix       R$ 100,00   (approved)
Payment #2: Cartao    R$ 100,00   (approved)
Payment #3: Dinheiro  R$ 100,00   (approved)

Soma pagamentos = R$ 300,00
payment_status = paid
```

**Regras de calculo:**
- `soma < total` → `payment_status = partial`
- `soma >= total` → `payment_status = paid`; troco = `soma - total`
- Um novo `Payment` pode ser adicionado enquanto `payment_status = partial`
- `Order.status` so muda para `paid` quando `payment_status = paid`

**Nao confunda:** registrar pagamento parcial nao fecha o pedido. A conta continua aberta para novos itens enquanto `Order.status = open`.

---

### 9.6 Cancelamento, cortesia e estorno

| Situacao | Acao | Modelo afetado |
|---|---|---|
| Item lancado errado, cozinha ainda nao fez | Void — `OrderItem.status = cancelled` | OrderItem |
| Cozinha ja fez, cliente reclamou | Comp — `OrderItem.status = comped` + desconto manual | OrderItem + Order |
| Cliente pagou e quer devolver | Refund — novo `Payment` com valor negativo | Payment + Order |
| Item foi para mesa errada | Mover item para outro pedido (futura feature) | OrderItem |
| Garcom saiu do turno | Transferir pedido para outro operador | Order.responsible_user |

**Regras:**
- `cancelled` so pode ser aplicado em itens `pending` (nao foram para cozinha)
- `comped` pode ser aplicado em qualquer status apos `sent` — o item aparece no relatorio mas com valor zerado
- Estorno (`refunded`) exige registro de motivo e aprovacao de gerente

---

### 9.7 Fluxo do caixa (Cash Register)

```
Abertura do turno
  → CashMovement: opening  (fundo de caixa inicial)

Durante o dia — a cada pagamento aprovado:
  → CashMovement: sale     (apenas metodos cash/dinheiro)

Sangrias (retirada de dinheiro):
  → CashMovement: withdrawal

Suprimentos (reposicao):
  → CashMovement: supply

Fechamento do turno:
  → Operador informa actual_amount (contagem fisica)
  → Sistema calcula expected_amount (abertura + entradas - saidas)
  → difference_amount = actual - expected
  → CashMovement: closing
```

---

### 9.8 Tabela de operacoes por tipo de estabelecimento

| Tipo | Pedido fica aberto? | Paga quando? | Particularidade |
|---|---|---|---|
| Restaurante com mesa | Sim — toda a refeicao | No final | Taxa de servico tipica (10%) |
| Bar por comanda | Sim — toda a noite | No final ou parcial | Comanda acumula rodadas |
| Lanchonete balcao | Nao — paga e pega | Na hora | payment_status=paid antes da producao |
| Cafeteria | Normalmente nao | Na hora | Igual balcao |
| Rodizio | Sim — taxa fixa | No final | Bebidas extras em rodadas |
| Delivery | Ate entregar | Antes ou na entrega | Entregador, zona e taxa |
| Retirada | Ate retirar | Antes ou na retirada | pickup_time registrado |
| Dark kitchen | Ate expedir | Normalmente antes | Sem atendimento presencial |

---

## 10. Autenticação e Permissões

### JWT

- **Access token:** duração 1 dia
- **Refresh token:** duração 7 dias, rotação ativa
- **Blacklist:** tokens invalidados ficam na blacklist
- O frontend armazena tokens em memória/localStorage e injeta via `Authorization: Bearer <token>` em cada request

### Middleware de Tenancy

- **`TenantMiddleware`** — intercepta todo request autenticado, injeta `request.tenant` (Account), `request.restaurant`, `request.branch` e o `UserProfile`
- **`TenantResponseSafetyMiddleware`** — valida que responses não extrapolam o escopo do tenant

### Escopos de Permissão

| profile_type | Acesso típico |
|---|---|
| `admin` | Tudo — acesso cross-restaurant |
| `owner` | Todos os dados do seu restaurante |
| `manager` | Operação completa: pedidos, cardápio, estoque, relatórios |
| `waiter` | PDV, pedidos, KDS |
| `cashier` | Caixa, pagamentos, PDV |
| `kitchen` | KDS — somente visualização e status de itens |
| `driver` | Entregas — visualização de pedidos tipo delivery |

### Permissões Granulares

Além do `profile_type`, cada `Role` tem `permissions` (M2M). Exemplos:
- `order.create`, `order.cancel`, `order.discount`
- `payment.refund`, `payment.view`
- `stock.adjustment`, `stock.view`
- `report.view`, `report.export`

---

## 11. Configurações do Ambiente

### Variáveis de Ambiente (`.env`)

```env
# Django
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=api.starchef.com.br

# Banco de dados
DATABASE_URL=postgresql://user:pass@localhost:5432/starchef

# Redis
REDIS_URL=redis://localhost:6379/0

# Email
EMAIL_HOST=smtp.mailgun.org
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=no-reply@starchef.com.br

# Sentry
SENTRY_DSN=...

# Frontend
VITE_API_BASE_URL=https://api.starchef.com.br/api/v1
VITE_WS_BASE_URL=wss://api.starchef.com.br
```

### Settings

| Setting | Dev | Prod |
|---|---|---|
| Banco | SQLite | PostgreSQL |
| Cache/Channels | In-memory | Redis |
| Celery | Eager (síncrono) | Worker + Beat |
| Debug | True | False |
| CORS | localhost:5173 | domínio do frontend |
| Sentry | Desativado | Ativo |

---

## 12. Rodando o Projeto

### Backend

```bash
# Instalar dependências
pip install -r requirements/dev.txt

# Banco de dados
python manage.py migrate

# Criar superusuário
python manage.py createsuperuser

# Dados de demo (se disponível)
python manage.py seed_demo

# Servidor de desenvolvimento
python manage.py runserver

# Ou com ASGI (WebSocket suportado)
daphne -p 8000 config.asgi:application

# Celery worker (em terminal separado)
celery -A config worker -l info

# Celery beat (agendamentos)
celery -A config beat -l info
```

### Frontend

```bash
cd frontend

# Instalar dependências
npm install

# Dev server (http://localhost:5173)
npm run dev

# Build de produção
npm run build
```

### Testes (Backend)

```bash
pytest
pytest --cov=apps tests/
```

---

## 13. Roadmap

### MVP — Implementado ✓

- [x] Autenticação JWT com refresh rotation
- [x] Multi-tenancy (Account → Restaurant → Branch)
- [x] Mesas, comandas e setores
- [x] Cardápio com produtos, variações e adicionais
- [x] Ficha técnica (receitas e ingredientes)
- [x] Abertura e fechamento de pedidos
- [x] Envio para cozinha
- [x] KDS em tempo real (WebSocket)
- [x] Formas de pagamento e registro de pagamento
- [x] Caixa com abertura/fechamento
- [x] Recibo simples
- [x] Dashboard operacional
- [x] Auditoria de ações
- [x] Gestão de usuários e perfis
- [x] CRUD genérico (ResourceListView + ResourceFormView)

### V2 — Próximos

- [ ] Ficha técnica com baixa automática de estoque
- [ ] Delivery completo (rastreamento, status do entregador)
- [ ] Relatórios avançados (vendas por período, margens por produto)
- [ ] Impressora térmica ESC/POS
- [ ] Promoções, combos e preços dinâmicos
- [ ] Notificações push (Web Push API)
- [ ] Exportação CSV/XLSX dos relatórios

### V3 — Futuro

- [ ] NFC-e / NF-e integrada (provedor fiscal)
- [ ] Gateway de pagamento (Stripe, Mercado Pago, Stone)
- [ ] Integração WhatsApp (pedidos via chat)
- [ ] Marketplace iFood / Rappi
- [ ] PWA com modo offline parcial
- [ ] Módulo de fidelidade e CRM
- [ ] App mobile nativo para KDS e entregadores
- [ ] Cobrança automática por plano (SaaS billing)
