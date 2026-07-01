# StarChef — Gap Analysis & Roadmap

> Análise do que já existe no sistema vs. o que é necessário para um SaaS de gestão de restaurante completo e competitivo.
> Gerado em: 2026-06-16

---

## 1. Estado atual do sistema

### Backend (Django REST)

| Módulo | Models | Endpoints | Status |
|---|---|---|---|
| Auth / RBAC | User, Role, Permission, UserProfile | login, logout, me, users, roles | ✅ Completo |
| Contas & Planos | Account, Plan, Subscription | accounts, plans, subscriptions | ✅ Completo |
| Restaurantes | Restaurant, Branch, TableSector, Table, Command | restaurants, branches, tables, sectors | ✅ Completo |
| Cardápio | ProductCategory, Product, ProductVariation, ProductAddon, Ingredient, Recipe, RecipeItem | menu/categories, products, addons, variations, ingredients | ✅ Completo (backend) |
| Pedidos | Order, OrderItem, OrderItemAddon | orders, items, send-to-kitchen, close, pay, cancel, print | ✅ Completo (backend) |
| Caixa / Pagamentos | PaymentMethod, Payment, CashRegister, CashMovement | payments, cash-register, open, close | ✅ Completo (backend) |
| Clientes | Customer, CustomerAddress | customers, addresses | ✅ Completo (backend) |
| Estoque | StockLocation, StockMovement | stock/locations, stock/movements | ⚠️ Parcial — sem baixa automática por venda |
| KDS | — (reutiliza Order/OrderItem) | kitchen/orders, kitchen/items, status | ⚠️ Parcial — sem WebSocket real-time |
| Impressão | Printer, PrintJob | printers, print-jobs | ⚠️ Parcial — driver ESC/POS não integrado |
| Fiscal | Invoice | invoices | ⚠️ Stub — nenhum provider fiscal integrado |
| Relatórios | — (computado) | reports/dashboard, reports/sales | ⚠️ Stub — sem DRE, CMV, fluxo de caixa |
| Auditoria | AuditLog | — | ⚠️ Backend pronto, sem exposição no frontend |
| Integrações | FiscalProvider (contrato) | — | ❌ Não implementado |
| Delivery próprio | — | — | ❌ Não implementado |
| CRM / Fidelização | — | — | ❌ Não implementado |
| Checklists | — | — | ❌ Não implementado |
| Chamados | — | — | ❌ Não implementado |
| Treinamentos | — | — | ❌ Não implementado |
| Comunicados | — | — | ❌ Não implementado |

### Frontend (Vue 3)

| Tela | Status |
|---|---|
| Login | ✅ Completo |
| Dashboard (KPIs) | ✅ Completo |
| KDS (lista estática) | ⚠️ Parcial — sem real-time, sem UI dedicada |
| Relatórios (vendas) | ⚠️ Parcial — sem DRE, CMV, exportação |
| ResourceListView (CRUD genérico) | ⚠️ Parcial — só lista, sem formulários de criação/edição |
| PDV (tela de venda) | ❌ Não existe |
| Formulários CRUD | ❌ Não existem |
| Cardápio digital público | ❌ Não existe |
| App garçom (mobile) | ❌ Não existe |
| Totem / autoatendimento | ❌ Não existe |
| Logs antifraude | ❌ Não existe (backend pronto) |
| Dashboard multiunidade | ❌ Não existe |

---

## 2. Gap Analysis por frente de negócio

### 2.1 Venda (PDV)

**Requisito:** Venda balcão, mesa, comanda, delivery, retirada, fechamento de caixa, sangria, suprimento, cancelamento e desconto com permissão.

| Item | Existe? | Observação |
|---|---|---|
| Order types: mesa, balcão, delivery, comanda, retirada | ✅ | Order model suporta todos os tipos |
| Abertura/fechamento de caixa | ✅ | CashRegister com open/close |
| Sangria e suprimento | ✅ | CashMovement types: withdrawal, supply |
| Cancelamento com permissão | ✅ | `CanAuthorizeDiscount` permission existe |
| Desconto por item/pedido | ✅ | discount_amount em Order e OrderItem |
| **Tela de PDV no frontend** | ❌ | Maior bloqueador — sistema não pode ser operado |
| Formulários de criação de pedido | ❌ | ResourceListView só lista |

### 2.2 Cardápio

**Requisito:** Link público, QR Code na mesa, adicionais, variações, observações, combos, disponibilidade por horário, taxa de entrega.

| Item | Existe? | Observação |
|---|---|---|
| Variações e adicionais | ✅ | ProductVariation e ProductAddon |
| Combos | ✅ | Product type: combo |
| Observações por item | ✅ | OrderItem.notes |
| Disponibilidade (ativo/inativo) | ✅ | Product.is_active |
| **Disponibilidade por horário** | ❌ | Nenhum campo de schedule no Product |
| **Link público de cardápio** | ❌ | Todas as rotas exigem autenticação |
| **QR Code gerado pelo sistema** | ❌ | Não implementado |
| **Taxa de entrega por zona** | ❌ | Sem modelo de zona de entrega |
| **Model Menu + MenuItem separados** | ❌ | Ver seção abaixo |

#### ⚠️ Problema estrutural: ausência de um model Menu

**Situação atual:** `Product` é vinculado diretamente à `branch` (via `TenantModel`). Não existe uma entidade `Menu` — o cardápio é implicitamente "todos os produtos ativos da filial".

**Por que isso é um problema:** cada restaurante pode precisar de múltiplos cardápios distintos — cardápio do salão, cardápio de delivery, cardápio de happy hour, cardápio digital público no QR Code, cardápio sazonal. Com a estrutura atual, isso é impossível sem duplicar produtos.

**Solução recomendada:** criar dois models novos:

```python
# apps/menu/models.py

class Menu(TenantModel):
    """Um cardápio é um agrupamento nomeado de produtos vinculado a um restaurante."""
    CHANNEL_ALL = "all"
    CHANNEL_TABLE = "table"
    CHANNEL_DELIVERY = "delivery"
    CHANNEL_COUNTER = "counter"
    CHANNEL_DIGITAL = "digital"   # link público / QR Code

    CHANNEL_CHOICES = [
        (CHANNEL_ALL, "Todos os canais"),
        (CHANNEL_TABLE, "Salão / Mesa"),
        (CHANNEL_DELIVERY, "Delivery"),
        (CHANNEL_COUNTER, "Balcão"),
        (CHANNEL_DIGITAL, "Cardápio digital público"),
    ]

    name = models.CharField(max_length=120)           # "Cardápio Principal", "Happy Hour", "Delivery"
    slug = models.SlugField(unique=True)              # usado na URL pública /menu/<slug>
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_ALL)
    is_active = models.BooleanField(default=True)
    available_from = models.TimeField(null=True, blank=True)   # disponível a partir de
    available_until = models.TimeField(null=True, blank=True)  # disponível até
    # branch já vem de TenantModel


class MenuItem(TenantModel):
    """Vínculo entre um Menu e um Product, com preço e ordem opcionais por cardápio."""
    menu = models.ForeignKey(Menu, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="menu_items", on_delete=models.CASCADE)
    display_order = models.PositiveIntegerField(default=0)
    override_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["menu", "product"], name="unique_product_per_menu"),
        ]
```

**Impacto nos outros módulos:**

| Módulo | Mudança necessária |
|---|---|
| Cardápio digital público | Rota `/menu/<slug>/` retorna os `MenuItem` do menu com `channel=digital` |
| QR Code | Gerado com URL `/menu/<slug>/` do menu vinculado à mesa |
| Delivery próprio | Order usa `Menu` com `channel=delivery` para filtrar produtos disponíveis |
| Disponibilidade por horário | `Menu.available_from/until` substitui o campo que seria no `Product` |
| PDV | Seletor de cardápio no início da venda (salão usa menu do salão, balcão usa o do balcão) |

> **Ação adicionada na Fase 1:** criar `Menu` + `MenuItem`, migrar os flags `available_for_table/counter/delivery` do `Product` para a lógica de `Menu.channel`, e expor endpoint público `/api/v1/public/menu/<slug>/`.

### 2.3 Cozinha / KDS

**Requisito:** Pedidos separados por setor, tempo de preparo, status, impressão térmica.

| Item | Existe? | Observação |
|---|---|---|
| Filtro por setor (cozinha, bar, sobremesa) | ✅ | kitchen/orders?sector=kitchen |
| Statuses por item | ✅ | pending → sent → preparing → ready → delivered |
| Tempo de preparo (configuração) | ✅ | Product.prep_time_minutes |
| **Tempo de preparo real (cronômetro)** | ❌ | Sem tracking de sent_at / ready_at por item |
| **WebSocket real-time** | ❌ | Channels + Redis prontos, nenhum Consumer criado |
| **Impressão ESC/POS real** | ❌ | PrintJob model existe, task Celery não criada |

### 2.4 Delivery próprio

**Requisito:** Área de entrega, taxa por bairro/km, motoboy, status, previsão, retirada.

| Item | Existe? | Observação |
|---|---|---|
| Order type: delivery / takeaway | ✅ | Tipos existem no Order model |
| Endereço de entrega via Customer | ✅ | CustomerAddress com lat/lng |
| **Modelo de zona de entrega** | ❌ | Não existe (DeliveryZone) |
| **Taxa por bairro ou raio** | ❌ | Não existe |
| **Motoboy (model + rastreio)** | ❌ | Não existe |
| **Status de entrega / previsão** | ❌ | Sem etapas após "saiu para entrega" |

### 2.5 Estoque e Ficha Técnica

**Requisito:** Ingredientes, baixa automática por venda, perda, validade, lote, estoque mínimo, sugestão de compra, CMV.

| Item | Existe? | Observação |
|---|---|---|
| Ingredientes | ✅ | Ingredient model |
| Ficha técnica (receita) | ✅ | Recipe + RecipeItem |
| Locais de estoque | ✅ | StockLocation |
| Movimentações manuais | ✅ | StockMovement (in/out/adjustment/inventory) |
| **Baixa automática por venda** | ❌ | Nenhum signal/service deduz ao fechar pedido |
| **CMV automático por prato** | ❌ | Product.cost é manual |
| **Estoque mínimo + alerta** | ❌ | Nenhum campo min_quantity |
| **Validade e lote** | ❌ | Sem campos expiry_date / batch |
| **Sugestão de compra** | ❌ | Não implementado |

### 2.6 Financeiro

**Requisito:** Caixa, contas a pagar/receber, despesas, fornecedores, DRE, fluxo de caixa, lucro por produto.

| Item | Existe? | Observação |
|---|---|---|
| Caixa (abertura/fechamento/movimentos) | ✅ | CashRegister + CashMovement |
| Formas de pagamento | ✅ | PaymentMethod + Payment |
| Histórico de recebimentos | ✅ | Payment read-only view |
| **Contas a pagar / receber** | ❌ | Sem AccountsPayable / AccountsReceivable |
| **Fornecedores** | ❌ | Sem Supplier model |
| **DRE** | ❌ | Sem visão de competência |
| **Fluxo de caixa** | ❌ | CashMovement é operacional, não financeiro |
| **Lucro por produto** | ❌ | Depende do CMV automático |

### 2.7 Fiscal

**Requisito:** NFC-e, NF-e, SAT/MFE, XML para contador, cancelamento/inutilização.

| Item | Existe? | Observação |
|---|---|---|
| Invoice model | ✅ | Fases: receipt/fiscal; statuses: draft/issued/cancelled/error |
| FiscalProvider contrato | ✅ | Interface definida em integrations/ |
| **Provider fiscal real** | ❌ | Nenhum integrado (Focus NFe, NFE.io, etc.) |
| **Geração e envio de NFC-e** | ❌ | Não implementado |
| **XML + DANFE** | ❌ | Campos existem no model, nunca preenchidos |
| **SAT/MFE** | ❌ | Não implementado |

### 2.8 Relatórios e BI

**Requisito:** Vendas por período/produto/garçom/canal/forma de pagamento, ticket médio, CMV, margem, desperdício.

| Item | Existe? | Observação |
|---|---|---|
| Vendas por período | ✅ | SalesReportView com date range |
| Vendas por forma de pagamento | ✅ | Agrupamento por payment_method |
| Vendas por filial | ✅ | Agrupamento por branch |
| Ticket médio | ✅ | Calculado no dashboard |
| Top produtos | ✅ | top_products no dashboard |
| **Vendas por garçom** | ❌ | Sem agrupamento por usuário |
| **CMV e margem por produto** | ❌ | Depende do CMV automático |
| **Desperdício** | ❌ | Sem tracking de perda |
| **Exportação CSV/Excel** | ❌ | Não implementado |
| **Metas e alertas** | ❌ | Não implementado |

### 2.9 Gestão de Rede / Operação

**Requisito:** Checklists, auditoria com score, planos de ação, chamados internos, treinamentos, comunicados.

| Item | Existe? | Observação |
|---|---|---|
| Multi-tenancy (account) | ✅ | Isolamento por Account |
| Multifilial (Branch) | ✅ | Branch com config por unidade |
| **Comparação entre unidades** | ❌ | Sem dashboard multiunidade |
| **Checklists operacionais** | ❌ | Nenhum model |
| **Auditoria com score** | ❌ | Nenhum model |
| **Chamados internos** | ❌ | Nenhum model |
| **Universidade corporativa** | ❌ | Nenhum model |
| **Comunicados** | ❌ | Nenhum model |
| **Logs antifraude (frontend)** | ❌ | AuditLog existe no backend, sem tela |

---

## 3. Ações por fase

### Fase 1 — MVP vendável
> Objetivo: sistema operável por um restaurante real hoje.

| # | Ação | Área | Impacto |
|---|---|---|---|
| 1 | **Formulários CRUD no frontend** (produto, pedido, cliente, categoria, ingrediente) | Frontend | 🔴 Crítico |
| 2 | **Tela de PDV completo** (mesa, balcão, comanda, delivery, desconto, fechamento) | Frontend | 🔴 Crítico |
| 3 | **KDS real-time com WebSocket** (Consumer Django Channels + reatividade no frontend) | Backend + Frontend | 🔴 Crítico |
| 4 | **Baixa automática de estoque por venda** (signal/service ao fechar pedido via RecipeItem) | Backend | 🔴 Crítico |
| 5 | **CMV automático por produto** (custo calculado via RecipeItem × StockMovement.unit_cost) | Backend | 🟠 Alta |
| 6 | **Cardápio digital público** (rota `/menu/:slug`, QR Code, disponibilidade por horário) | Backend + Frontend | 🟠 Alta |
| 7 | **Delivery próprio** (DeliveryZone, taxa por bairro/km, Deliveryman model, status de entrega) | Backend | 🟠 Alta |
| 8 | **Impressão ESC/POS real** (task Celery que envia bytes ao PrintJob driver escpos) | Backend | 🟡 Média |

### Fase 2 — Produto forte
> Objetivo: competir com Saipos, Sischef e Anota AI.

| # | Ação | Área | Impacto |
|---|---|---|---|
| 9 | **Fiscal NFC-e / NF-e** (integrar FiscalProvider com Focus NFe ou NFE.io) | Backend | 🔴 Crítico (mercado formal) |
| 10 | **Integração iFood / Rappi** (webhook receiver, mapeamento para Order) | Backend | 🔴 Crítico (volume) |
| 11 | **WhatsApp Business** (chatbot de pedidos via Evolution API ou Cloud API) | Backend | 🟠 Alta |
| 12 | **CRM de clientes** (histórico agregado, segmentação, alerta de inativo, recompra) | Backend + Frontend | 🟠 Alta |
| 13 | **Fidelização** (Coupon, Cashback, LoyaltyPoints, resgate no checkout) | Backend | 🟠 Alta |
| 14 | **DRE + Contas a pagar/receber** (Supplier, AccountsPayable, AccountsReceivable, DRE view) | Backend + Frontend | 🟠 Alta |
| 15 | **App garçom PWA** (interface mobile para lançar pedido na mesa e fechar conta) | Frontend | 🟡 Média |
| 16 | **Totem / autoatendimento** (rota pública por QR Code, pedido + pagamento online) | Frontend | 🟡 Média |

### Fase 3 — SaaS completo e escalável
> Objetivo: atender redes, franquias e grupos com múltiplas unidades.

| # | Ação | Área | Impacto |
|---|---|---|---|
| 17 | **Checklists operacionais** (Checklist, ChecklistItem, ChecklistExecution, fotos, geo) | Backend | 🟠 Alta (rede) |
| 18 | **Auditoria com score** (AuditVisit, nota por unidade, ranking, plano de ação) | Backend | 🟠 Alta (rede) |
| 19 | **Chamados internos** (Ticket, SLA, responsável, histórico) | Backend | 🟡 Média |
| 20 | **Universidade corporativa** (Training, Module, Quiz, Certificate, TrainingProgress) | Backend | 🟡 Média |
| 21 | **Comunicados** (Announcement, confirmação de leitura, urgência, anexos) | Backend | 🟡 Média |
| 22 | **Dashboard multiunidade** (comparação de filiais: venda, CMV, tempo, reclamação) | Frontend | 🟠 Alta (rede) |
| 23 | **Frontend de logs antifraude** (tela que consome AuditLog: cancelamentos, descontos, caixa) | Frontend | 🟡 Média |
| 24 | **BI avançado** (metas, alertas, previsões, exportação CSV/Excel) | Backend + Frontend | 🟡 Média |
| 25 | **API pública + webhooks** (API key por conta, webhooks para pedido/pagamento) | Backend | 🟡 Média |
| 26 | **Modo offline / PWA service worker** (PDV funciona sem internet, sincroniza ao reconectar) | Frontend | 🟡 Média |

---

## 4. Dependências técnicas entre ações

```
Baixa automática (4) ──────────────────► CMV automático (5)
                                               │
                                               ▼
                              DRE / Lucro por produto (14)

Tela PDV (2) ─────► KDS real-time (3) ─────► App garçom (15)

Cardápio público (6) ────────────────────────► Totem autoatendimento (16)

Fiscal (9) ──────────────────────────────────► API pública (25)

iFood/Rappi (10) ──────────────────────────► Dashboard multiunidade (22)
WhatsApp (11) ────────────────────────────────► CRM (12) ───► Fidelização (13)

Checklists (17) ─────────────────────────────► Auditoria com score (18)
                                                      │
                                                      ▼
                                              Planos de ação (dentro de 18)
```

---

## 5. Checklist final do SaaS completo

```
VENDA
  [ ] PDV completo (mesa, comanda, balcão, delivery, retirada)
  [ ] App garçom PWA
  [ ] Totem / autoatendimento com QR Code

ATENDIMENTO
  [ ] Cardápio digital público com QR Code
  [ ] Chatbot WhatsApp (pedido automatizado)
  [ ] CRM (histórico, inativo, recompra)
  [ ] Cupom / cashback / fidelidade

PRODUÇÃO
  [ ] KDS real-time (WebSocket)
  [ ] Impressão ESC/POS via Celery
  [ ] Cronômetro de tempo de preparo por item

ENTREGA
  [ ] Delivery próprio (zona, taxa, motoboy, rastreio)
  [ ] Integração iFood / Rappi

ESTOQUE
  [ ] Baixa automática por venda (ficha técnica)
  [ ] Estoque mínimo + alerta
  [ ] Validade e lote
  [ ] CMV automático por produto

FINANCEIRO
  [ ] Fornecedores + contas a pagar/receber
  [ ] DRE e fluxo de caixa
  [ ] Lucro por produto

FISCAL
  [ ] NFC-e / NF-e (provider real)
  [ ] XML + DANFE para contador
  [ ] Cancelamento / inutilização

GESTÃO
  [ ] Permissões granulares (além de profile_type)
  [ ] Logs antifraude no frontend
  [ ] Dashboard multiunidade

OPERAÇÃO (rede / franquia)
  [ ] Checklists operacionais
  [ ] Auditoria com score por unidade
  [ ] Chamados internos com SLA
  [ ] Universidade corporativa
  [ ] Comunicados com confirmação de leitura

BI
  [ ] Relatórios por garçom, produto, canal, margem
  [ ] Exportação CSV / Excel
  [ ] Metas e alertas
  [ ] Modo offline / PWA

PLATAFORMA
  [ ] API pública com autenticação por chave
  [ ] Webhooks para pedido / pagamento / estoque
```

---

## 6. Resumo executivo

O backend está **surpreendentemente maduro**: 32 models, lifecycle completo de pedidos com 9 statuses, multi-tenancy, Celery, Django Channels e Redis já configurados. A base técnica está pronta para suportar todas as fases.

O **maior bloqueador hoje é o frontend**: sem formulários CRUD e tela de PDV, o sistema não pode ser operado por nenhum restaurante. Este é o ponto de partida obrigatório.

Em seguida, a **baixa automática de estoque** e o **CMV automático** são fundamentais — sem eles, o financeiro é cego. Com essas duas peças, o sistema passa a calcular lucro real por prato.

A **fiscal** (NFC-e/NF-e) e a **integração com iFood** são os maiores aceleradores de vendas: a primeira abre o mercado formal, a segunda traz volume imediato.

A camada de **gestão de rede** (checklists, auditoria, chamados, treinamentos) é o diferencial para escalar de restaurante individual para redes e franquias — e é onde quase nenhum concorrente é forte ao mesmo tempo que tem PDV.
