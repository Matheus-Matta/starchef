/**
 * Schema declarativo de todos os recursos CRUD do sistema.
 *
 * Cada entrada descreve uma "model" da API e dirige, sem codigo por tela:
 *  - a listagem       (`columns`)
 *  - o formulario      (`formFields`, opcional -> recurso somente-leitura sem ele)
 *  - as rotas          (geradas em router/index.js a partir de `name`)
 *  - o detalhe (view)  (colunas + config visual em config/detailMeta.js)
 *
 * Campos de coluna:  { key, label, type?, map?, align?, value? }
 *   type: "status" | "money" | "date" | "boolean" | (texto por padrao)
 * Campos de formulario: { name, label, type, required?, options?, endpoint?, full?, default? }
 *   type: text | number | decimal | textarea | password | boolean | dropdown | remote-dropdown
 */
import {
  CHANNEL_OPTIONS,
  COMMAND_STATUS_LABELS,
  EMISSION_TYPE_LABELS,
  FISCAL_CSOSN_OPTIONS,
  FISCAL_CST_ICMS_OPTIONS,
  FISCAL_CST_PIS_COFINS_OPTIONS,
  FISCAL_ORIGEM_OPTIONS,
  INVOICE_STATUS_LABELS,
  MENU_CHANNEL_LABELS,
  MOVEMENT_TYPE_LABELS,
  DELIVERY_STATUS_LABELS,
  ORDER_TYPE_LABELS,
  PAYMENT_STATUS_LABELS,
  PRODUCTION_STATUS_LABELS,
  TERMINAL_ROLE_LABELS,
  TERMINAL_ROLE_OPTIONS,
  TERMINAL_TYPE_LABELS,
  TERMINAL_TYPE_OPTIONS,
  PAYMENT_METHOD_TYPE_LABELS,
  PAYMENT_TYPE_OPTIONS,
  PRICING_OPTIONS,
  PRINTER_DRIVER_LABELS,
  PRINTER_CONNECTION_LABELS,
  PRINTER_DRIVER_OPTIONS,
  PRINTER_CONNECTION_OPTIONS,
  PRODUCT_TYPE_OPTIONS,
  SLA_PRIORITY_LABELS,
  SLA_PRIORITY_OPTIONS,
  SLA_TYPE_LABELS,
  SLA_TYPE_OPTIONS,
  PROFILE_TYPE_LABELS,
  PROFILE_TYPE_OPTIONS,
  SCALE_PROTOCOL_LABELS,
  SCALE_PROTOCOL_OPTIONS,
  SECTOR_OPTIONS,
  TABLE_STATUS_LABELS,
  UNIT_OPTIONS,
  VEHICLE_OPTIONS,
  VEHICLE_TYPE_LABELS,
} from "./enums";

export const resources = [
  // ── Operacional ────────────────────────────────────────────────────
  {
    name: "pedidos",
    title: "Pedidos",
    endpoint: "/orders/",
    // Configuração "pro" desta tela: ação primária, filtro de período e filtros rápidos.
    pro: {
      pageSize: 12,
      // Ação primária do cabeçalho — Pedidos são criados no PDV.
      primaryAction: { label: "Novo pedido", icon: "pi pi-plus", route: "pdv" },
      // Filtro de intervalo de datas → envia `opened_after` / `opened_before`.
      dateField: { param: "opened", label: "Período" },
      // Filtros rápidos por status — reservados para os "filtros avançados" (a implementar).
      quickFilters: [
        { key: "pending", label: "Aguardando pagamento", filter: { payment_status: "pending" } },
        { key: "partial", label: "Pagamento parcial", filter: { payment_status: "partial" } },
        { key: "paid", label: "Pagos", filter: { payment_status: "paid" } },
        { key: "refunded", label: "Estornados", filter: { payment_status: "refunded" } },
      ],
    },
    columns: [
      { key: "sequence", label: "Pedido" },
      { key: "order_type", label: "Tipo", map: ORDER_TYPE_LABELS },
      { key: "command_number", label: "Comanda" },
      { key: "table_number", label: "Mesa" },
      { key: "customer_name", label: "Cliente" },
      { key: "total", label: "Total", type: "money", align: "right" },
      // Status separados: preparação, pagamento e entrega (esta só com o módulo).
      { key: "production_status", label: "KDS", type: "kds", map: PRODUCTION_STATUS_LABELS },
      { key: "payment_status", label: "Pagamento", type: "status", map: PAYMENT_STATUS_LABELS },
      { key: "delivery_status", label: "Entrega", type: "status", map: DELIVERY_STATUS_LABELS, module: "entrega" },
      { key: "opened_at", label: "Aberto", type: "date" },
    ],
  },
  {
    name: "sla",
    title: "SLAs",
    endpoint: "/sla/",
    globalScope: true,
    columns: [
      { key: "name", label: "Nome" },
      { key: "sla_type", label: "Tipo", type: "status", map: SLA_TYPE_LABELS },
      { key: "target_minutes", label: "Tempo-alvo (min)", align: "right" },
      { key: "alert_minutes", label: "Alerta (min)", align: "right" },
      { key: "priority", label: "Prioridade", map: SLA_PRIORITY_LABELS },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do SLA", type: "text", required: true, full: true, section: "SLA" },
      { name: "sla_type", label: "Tipo", type: "dropdown", options: SLA_TYPE_OPTIONS, default: "prep", section: "SLA" },
      { name: "priority", label: "Prioridade", type: "dropdown", options: SLA_PRIORITY_OPTIONS, default: "normal", section: "SLA" },
      { name: "target_minutes", label: "Tempo-alvo (min)", type: "number", default: 15, section: "Tempos" },
      { name: "alert_minutes", label: "Limite de alerta (min)", type: "number", default: 10, section: "Tempos" },
      // Vincula o SLA a vários restaurantes via MultiSelect do PrimeVue (STC-066).
      { name: "restaurants", label: "Restaurantes vinculados", type: "remote-multiselect", endpoint: "/restaurants/", optionLabel: "trade_name", optionValue: "id", full: true, section: "Abrangência" },
      // Um SLA é reutilizável: pode ser aplicado a vários quadros (estações) e/ou colunas.
      { name: "stations", label: "Quadros (estações KDS)", type: "remote-multiselect", endpoint: "/kitchen/stations/", optionLabel: "name", optionValue: "id", globalScope: true, full: true, section: "Aplicar no KDS", hint: "O SLA vale para todas as colunas destes quadros." },
      { name: "columns", label: "Colunas específicas", type: "remote-multiselect", endpoint: "/kitchen/columns/", optionLabel: "label", optionValue: "id", globalScope: true, full: true, section: "Aplicar no KDS", hint: "Cards parados nestas colunas alertam após o tempo-alvo. A coluna tem prioridade sobre o quadro." },
      { name: "is_active", label: "Ativo", type: "boolean", default: true, section: "SLA" },
    ],
  },
  {
    name: "kds-estacoes",
    title: "Estacoes KDS",
    endpoint: "/kitchen/stations/",
    columns: [
      { key: "name", label: "Estacao" },
      { key: "restaurant_name", label: "Restaurante" },
      { key: "sla_minutes", label: "SLA (min)", align: "right" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome da estacao", type: "text", required: true },
      { name: "restaurant", label: "Restaurante", type: "remote-dropdown", endpoint: "/restaurants/", optionLabel: "trade_name", optionValue: "id", required: true, globalScope: true },
      { name: "sla_minutes", label: "SLA em minutos", type: "number", default: 15 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "mesas",
    title: "Mesas",
    endpoint: "/tables/",
    // Ações: ver códigos por linha; imprimir etiquetas em lote (seleção).
    pro: {
      headerActions: [{ key: "bulk", label: "Criar em lote", icon: "pi pi-clone", type: "bulk-create", bulkType: "tables" }],
      bulkActions: [{ key: "print-codes", label: "Imprimir etiquetas", icon: "pi pi-print", type: "print-codes" }],
      rowActions: [{ key: "codes", label: "Ver códigos", icon: "pi pi-qrcode", type: "codes" }],
    },
    columns: [
      { key: "number", label: "Mesa" },
      { key: "code", label: "Código" },
      { key: "sector_name", label: "Setor" },
      { key: "capacity", label: "Lugares" },
      { key: "status", label: "Status", type: "status", map: TABLE_STATUS_LABELS },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "number", label: "Numero da mesa", type: "text", required: true },
      { name: "code", label: "Código de barras/QR (opcional)", type: "text", placeholder: "Auto = número da mesa" },
      { name: "sector", label: "Setor", type: "remote-dropdown", endpoint: "/tables/sectors/", optionLabel: "name", optionValue: "id", required: true },
      { name: "capacity", label: "Capacidade (lugares)", type: "number", default: 4 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "comandas",
    title: "Comandas",
    endpoint: "/commands/",
    // Comanda reutilizável (padrão self-service): número por restaurante + código
    // de barras/QR. Ação de cabeçalho cria muitas de uma vez; ação por linha
    // exibe/imprime os códigos do cartão.
    pro: {
      bulkDeleteEndpoint: "/commands/bulk-delete/",
      bulkUpdateEndpoint: "/commands/bulk-update/",
      headerActions: [{ key: "bulk", label: "Criar em lote", icon: "pi pi-clone", type: "bulk-create", bulkType: "commands" }],
      bulkActions: [{ key: "print-codes", label: "Imprimir etiquetas", icon: "pi pi-print", type: "print-codes" }],
      rowActions: [{ key: "codes", label: "Ver códigos", icon: "pi pi-qrcode", type: "codes" }],
    },
    columns: [
      { key: "number", label: "Comanda" },
      { key: "code", label: "Código" },
      { key: "customer_name", label: "Cliente" },
      { key: "status", label: "Status", type: "status", map: COMMAND_STATUS_LABELS },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "number", label: "Número da comanda (opcional)", type: "number", placeholder: "Auto = próximo número do restaurante" },
      { name: "code", label: "Código de barras/QR (opcional)", type: "text", placeholder: "Auto a partir do número" },
      { name: "customer_name", label: "Cliente (opcional)", type: "text" },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "clientes",
    title: "Clientes",
    endpoint: "/customers/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "phone", label: "Telefone" },
      { key: "email", label: "Email" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome completo", type: "text", required: true, full: true, section: "Dados pessoais" },
      { name: "document", label: "CPF", type: "text", placeholder: "000.000.000-00", section: "Dados pessoais" },
      { name: "birth_date", label: "Data de nascimento", type: "text", inputType: "date", section: "Dados pessoais" },
      { name: "phone", label: "Telefone", type: "text", placeholder: "(11) 90000-0000", section: "Contato" },
      { name: "email", label: "Email", type: "text", inputType: "email", section: "Contato" },
      { name: "internal_notes", label: "Observacoes", type: "textarea", full: true, section: "Contato" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true, section: "Contato" },
      { name: "address.label", label: "Identificacao", type: "text", default: "Principal", placeholder: "Casa, trabalho...", section: "Endereco principal" },
      { name: "address.zip_code", label: "CEP", type: "text", placeholder: "00000-000", section: "Endereco principal" },
      { name: "address.street", label: "Rua / Avenida", type: "text", full: true, section: "Endereco principal" },
      { name: "address.number", label: "Numero", type: "text", section: "Endereco principal" },
      { name: "address.complement", label: "Complemento", type: "text", section: "Endereco principal" },
      { name: "address.district", label: "Bairro", type: "text", section: "Endereco principal" },
      { name: "address.city", label: "Cidade", type: "text", section: "Endereco principal" },
      { name: "address.state", label: "UF", type: "text", placeholder: "SP", maxlength: 2, section: "Endereco principal" },
      { name: "address.reference", label: "Ponto de referencia", type: "textarea", full: true, rows: 2, section: "Endereco principal" },
    ],
  },
  {
    name: "caixa",
    title: "Caixa",
    endpoint: "/cash-register/",
    columns: [
      { key: "status", label: "Status", type: "status", map: { open: "Aberto", closed: "Fechado" } },
      { key: "opening_amount", label: "Abertura", type: "money", align: "right" },
      { key: "expected_amount", label: "Esperado", type: "money", align: "right" },
      { key: "opened_at", label: "Aberto em", type: "date" },
      { key: "closed_at", label: "Fechado em", type: "date" },
    ],
  },

  // ── Cardapio ───────────────────────────────────────────────────────
  {
    name: "cardapio",
    title: "Produtos",
    endpoint: "/menu/products/",
    columns: [
      { key: "internal_code", label: "Codigo" },
      { key: "ean", label: "Cód. barras" },
      { key: "name", label: "Produto" },
      { key: "restaurant_names", label: "Restaurantes", type: "badges", sortable: false },
      { key: "category_name", label: "Categoria" },
      { key: "current_price", label: "Preco", type: "money", align: "right" },
      { key: "sector_name", label: "Setor" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      // Seções (STC-021): informações básicas, preços, classificação, disponibilidade, produção.
      { name: "name", label: "Nome do produto", type: "text", required: true, full: true, section: "Informações básicas" },
      { name: "restaurants", label: "Restaurantes que utilizam o produto", type: "remote-multiselect", endpoint: "/restaurants/", optionLabel: "trade_name", optionValue: "id", globalScope: true, required: true, full: true, section: "Informações básicas", hint: "Disponibilize o mesmo produto em vários restaurantes da franquia." },
      { name: "internal_code", label: "Codigo interno", type: "text", section: "Informações básicas" },
      // Texto, nunca número: `0000012345670` e `12345670` são códigos
      // diferentes, e perder os zeros faria o leitor não achar o produto.
      { name: "ean", label: "Código de barras (EAN/GTIN)", type: "text", placeholder: "7891000100103", section: "Informações básicas", hint: "Opcional e único na conta. O PDV usa este código na leitura do scanner; o dígito verificador é conferido no salvamento." },
      { name: "description", label: "Descricao", type: "textarea", full: true, section: "Informações básicas" },
      { name: "sector", label: "Setor principal (opcional)", type: "remote-dropdown", endpoint: "/tables/sectors/", optionLabel: "name", optionValue: "id", section: "Informações básicas" },
      { name: "sale_price", label: "Preco de venda (R$)", type: "decimal", required: true, section: "Preços" },
      { name: "promotional_price", label: "Preco promocional (R$)", type: "decimal", section: "Preços" },
      { name: "pricing_unit", label: "Cobranca", type: "dropdown", options: PRICING_OPTIONS, default: "unit", section: "Preços" },
      // Categoria opcional (STC-022): pode ficar vazia — o produto aparece como "Sem categoria".
      { name: "category", label: "Categoria", type: "remote-dropdown", endpoint: "/menu/categories/", optionLabel: "name", optionValue: "id", placeholder: "Sem categoria", section: "Classificação" },
      { name: "product_type", label: "Tipo de produto", type: "dropdown", options: PRODUCT_TYPE_OPTIONS, default: "meal", section: "Classificação" },
      // Perfil fiscal (NCM/CFOP/CSOSN/aliquotas) usado ao emitir NFC-e. O mesmo
      // perfil serve vários produtos (1:N) e é cadastrado em Financeiro › Perfis fiscais.
      { name: "fiscal_profile", label: "Perfil fiscal", type: "remote-dropdown", endpoint: "/fiscal/profiles/", optionLabel: "name", optionValue: "id", placeholder: "Sem perfil (item sai sem tributação)", module: "financeiro", section: "Classificação", quickCreate: "fiscal-profile", hint: "Grupo tributário reutilizável. Cadastre em Financeiro › Perfis fiscais ou crie um novo no \"+\"." },
      { name: "average_preparation_time", label: "Tempo de preparo (min)", type: "number", default: 15, section: "Produção e logística" },
      // Campo do Modulo Logistica: controle de estoque so faz sentido com o modulo.
      { name: "controls_stock", label: "Controla estoque", type: "boolean", default: false, module: "logistica", section: "Produção e logística" },
      // Switches de disponibilidade — alinhados em grid na seção "Disponibilidade".
      { name: "available_for_table", label: "Disponivel para mesa", type: "boolean", default: true, section: "Disponibilidade" },
      { name: "available_for_counter", label: "Disponivel para balcao", type: "boolean", default: true, section: "Disponibilidade" },
      // Campo do Modulo Entrega: so aparece se a conta tiver o modulo habilitado.
      { name: "available_for_delivery", label: "Disponivel para delivery", type: "boolean", default: true, module: "entrega", section: "Disponibilidade" },
      // Switches de permissão — alinhados em grid na seção "Permissões".
      { name: "allows_addons", label: "Permite adicionais", type: "boolean", default: true, section: "Permissões" },
      { name: "allows_notes", label: "Permite observacoes", type: "boolean", default: true, section: "Permissões" },
      { name: "requires_variation", label: "Exigir escolha de variacao", type: "boolean", default: false, section: "Permissões" },
      // "Ativo" isolado e destacado, em sua própria seção.
      { name: "is_active", label: "Ativo", type: "boolean", default: true, section: "Status" },
    ],
  },
  {
    name: "categorias",
    title: "Categorias",
    endpoint: "/menu/categories/",
    // Compartilhadas entre restaurantes (reutilizáveis) — sem vínculo obrigatório.
    sharedAcrossRestaurants: true,
    columns: [
      { key: "name", label: "Nome" },
      { key: "display_order", label: "Ordem" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "display_order", label: "Ordem de exibicao", type: "number", default: 0 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "ingredientes",
    title: "Ingredientes",
    endpoint: "/menu/ingredients/",
    // Compartilhados entre restaurantes (reutilizáveis) — sem vínculo obrigatório.
    sharedAcrossRestaurants: true,
    // Regra de negocio (Modulo Base): o ingrediente serve para composicao/ficha
    // tecnica, SEM dados de custo/preco. Custo e estoque sao do Modulo Logistica.
    columns: [
      { key: "name", label: "Ingrediente" },
      { key: "unit", label: "Unidade" },
      { key: "minimum_stock", label: "Estoque min.", align: "right" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true, section: "Identificação" },
      { name: "unit", label: "Unidade de medida", type: "dropdown", options: UNIT_OPTIONS, section: "Identificação" },
      // Estoque mínimo (STC-031/032): opcional e só aparece com o Módulo Logística.
      { name: "minimum_stock", label: "Estoque minimo", type: "decimal", module: "logistica", section: "Logística" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true, section: "Identificação" },
    ],
  },
  {
    name: "receitas",
    title: "Receitas",
    endpoint: "/menu/recipes/",
    columns: [
      { key: "product.name", label: "Produto" },
      { key: "yield_quantity", label: "Rendimento" },
      { key: "total_cost", label: "Custo total", type: "money", align: "right" },
      { key: "auto_deduct_stock", label: "Baixa auto.", type: "boolean" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "product", label: "Produto", type: "remote-dropdown", endpoint: "/menu/products/", optionLabel: "name", optionValue: "id", required: true, section: "Receita" },
      { name: "yield_quantity", label: "Rendimento (porções)", type: "decimal", default: 1, section: "Receita" },
      // Baixa automática de estoque é comportamento do Módulo Logística.
      { name: "auto_deduct_stock", label: "Baixa automática de estoque", type: "boolean", default: true, module: "logistica", section: "Receita" },
      { name: "is_active", label: "Ativa", type: "boolean", default: true, section: "Receita" },
    ],
  },
  {
    name: "cardapios",
    module: "ecommerce",
    title: "Cardapios",
    endpoint: "/menu/menus/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "slug", label: "Slug" },
      { key: "channel", label: "Canal", map: MENU_CHANNEL_LABELS },
      { key: "available_from", label: "Disponivel de" },
      { key: "available_until", label: "Disponivel ate" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "slug", label: "Slug (URL)", type: "text", placeholder: "ex: almoco-segunda" },
      { name: "channel", label: "Canal", type: "dropdown", options: CHANNEL_OPTIONS },
      { name: "available_from", label: "Disponivel de (HH:MM)", type: "text", placeholder: "08:00" },
      { name: "available_until", label: "Disponivel ate (HH:MM)", type: "text", placeholder: "22:00" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "adicionais",
    title: "Adicionais",
    endpoint: "/menu/addons/",
    // Compartilhados entre restaurantes (reutilizáveis) — sem vínculo obrigatório.
    sharedAcrossRestaurants: true,
    columns: [
      { key: "name", label: "Adicional" },
      { key: "price", label: "Preco", type: "money", align: "right" },
      { key: "production_sector", label: "Setor" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "price", label: "Preco (R$)", type: "decimal", required: true },
      { name: "production_sector", label: "Setor", type: "dropdown", options: SECTOR_OPTIONS },
      // O vínculo com produtos é gerenciado na edição do PRODUTO (não aqui).
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },

  // ── Estoque ────────────────────────────────────────────────────────
  {
    name: "estoque",
    module: "logistica",
    title: "Estoque",
    endpoint: "/stock/movements/",
    columns: [
      { key: "ingredient_name", label: "Ingrediente" },
      { key: "location_name", label: "Local" },
      { key: "movement_type", label: "Movimento", type: "status", map: MOVEMENT_TYPE_LABELS },
      { key: "quantity", label: "Qtd.", align: "right" },
      { key: "total_cost", label: "Custo", type: "money", align: "right" },
      { key: "created_at", label: "Data", type: "date" },
    ],
  },
  {
    name: "locais-estoque",
    module: "logistica",
    title: "Locais de Estoque",
    endpoint: "/stock/locations/",
    columns: [
      { key: "name", label: "Local" },
      { key: "description", label: "Descricao" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do local", type: "text", required: true },
      { name: "description", label: "Descricao", type: "textarea", full: true },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },

  // ── Delivery ───────────────────────────────────────────────────────
  {
    name: "zonas-entrega",
    module: "entrega",
    title: "Zonas de Entrega",
    endpoint: "/delivery/zones/",
    columns: [
      { key: "name", label: "Zona" },
      { key: "min_radius_km", label: "Raio min. (km)", align: "right" },
      { key: "max_radius_km", label: "Raio max. (km)", align: "right" },
      { key: "delivery_fee", label: "Taxa", type: "money", align: "right" },
      { key: "estimated_minutes", label: "Tempo (min)", align: "right" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome da zona", type: "text", required: true },
      { name: "min_radius_km", label: "Raio minimo (km)", type: "decimal" },
      { name: "max_radius_km", label: "Raio maximo (km)", type: "decimal" },
      { name: "delivery_fee", label: "Taxa de entrega (R$)", type: "decimal" },
      { name: "estimated_minutes", label: "Tempo estimado (min)", type: "number" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "entregadores",
    module: "entrega",
    title: "Entregadores",
    endpoint: "/delivery/deliverymen/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "phone", label: "Telefone" },
      { key: "vehicle_type", label: "Veiculo", map: VEHICLE_TYPE_LABELS },
      { key: "vehicle_plate", label: "Placa" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome completo", type: "text", required: true },
      { name: "phone", label: "Telefone", type: "text" },
      { name: "vehicle_type", label: "Tipo de veiculo", type: "dropdown", options: VEHICLE_OPTIONS },
      { name: "vehicle_plate", label: "Placa", type: "text" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },

  // ── Pagamentos ─────────────────────────────────────────────────────
  {
    // A forma de pagamento pertence a UM restaurante (PaymentMethod é TenantModel) e
    // todo restaurante novo nasce com o mesmo conjunto padrão (apps/payments/defaults.py):
    // com mais de um restaurante a conta tem vários "Dinheiro"/"PIX" homônimos. Por isso
    // NÃO é `globalScope` — a lista segue o restaurante do seletor do topo e o formulário
    // ganha o campo "Restaurante" (injetado por ResourceFormView) — e a coluna
    // `restaurant_name` distingue os homônimos quando o escopo é "Todos".
    name: "formas-pagamento",
    title: "Formas de Pagamento",
    endpoint: "/payments/methods/",
    columns: [
      { key: "name", label: "Forma" },
      { key: "restaurant_name", label: "Restaurante" },
      { key: "method_type", label: "Tipo", map: PAYMENT_METHOD_TYPE_LABELS },
      { key: "requires_reference", label: "Exige referencia", type: "boolean" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "method_type", label: "Tipo", type: "dropdown", required: true, options: PAYMENT_TYPE_OPTIONS },
      { name: "requires_reference", label: "Exige referencia", type: "boolean", default: false },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "pagamentos",
    module: "financeiro",
    title: "Historico de Pagamentos",
    endpoint: "/payments/",
    globalScope: true,
    columns: [
      { key: "order", label: "Pedido" },
      { key: "payment_method_name", label: "Forma" },
      { key: "amount", label: "Valor", type: "money", align: "right" },
      { key: "change_amount", label: "Troco", type: "money", align: "right" },
      { key: "created_at", label: "Data", type: "date" },
    ],
  },

  // ── Fiscal ─────────────────────────────────────────────────────────
  {
    name: "notas-fiscais",
    module: "financeiro",
    title: "Notas Fiscais",
    endpoint: "/invoices/",
    globalScope: true,
    columns: [
      { key: "number", label: "Numero" },
      { key: "phase", label: "Tipo" },
      { key: "status", label: "Status", type: "status", map: INVOICE_STATUS_LABELS },
      { key: "emission_type", label: "Emissao", type: "status", map: EMISSION_TYPE_LABELS },
      { key: "total_amount", label: "Valor", type: "money", align: "right" },
      { key: "issued_at", label: "Emissao em", type: "date" },
    ],
  },
  {
    // Grupo tributario reutilizavel: quem escolhe o perfil e o PRODUTO (1:N),
    // igual a categoria. Nao pertence a restaurante nenhum — e da conta.
    name: "perfis-fiscais",
    module: "financeiro",
    title: "Perfis Fiscais",
    endpoint: "/fiscal/profiles/",
    sharedAcrossRestaurants: true,
    columns: [
      { key: "name", label: "Perfil" },
      { key: "ncm", label: "NCM" },
      { key: "cfop", label: "CFOP" },
      { key: "csosn", label: "CSOSN" },
      { key: "cst_icms", label: "CST ICMS" },
      { key: "is_default", label: "Padrao", type: "boolean" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do perfil", type: "text", required: true, full: true, placeholder: "Ex.: Bebida, Prato padrao", section: "Identificacao", hint: "Como voce vai reconhecer este grupo tributario ao cadastrar um produto." },
      { name: "ncm", label: "NCM", type: "text", placeholder: "22021000", section: "Classificacao", hint: "8 digitos. Obrigatorio na NF-e/NFC-e." },
      { name: "cest", label: "CEST", type: "text", placeholder: "0300100", section: "Classificacao", hint: "Somente para produtos sujeitos a substituicao tributaria." },
      { name: "cfop", label: "CFOP de venda", type: "text", default: "5102", placeholder: "5102", section: "Classificacao", hint: "5102 = venda dentro do estado. 6102 = fora do estado." },
      { name: "origem", label: "Origem da mercadoria", type: "dropdown", options: FISCAL_ORIGEM_OPTIONS, default: "0", section: "Classificacao" },
      { name: "csosn", label: "CSOSN (Simples Nacional)", type: "dropdown", options: FISCAL_CSOSN_OPTIONS, placeholder: "Selecione se a empresa e do Simples", section: "ICMS", hint: "Use este campo quando o CRT da empresa for Simples Nacional." },
      { name: "cst_icms", label: "CST ICMS (Regime Normal)", type: "dropdown", options: FISCAL_CST_ICMS_OPTIONS, placeholder: "Selecione se a empresa e do Regime Normal", section: "ICMS", hint: "Preencha CSOSN ou CST ICMS — o que valer para o enquadramento da empresa." },
      { name: "icms_rate", label: "Aliquota ICMS (%)", type: "decimal", default: 0, section: "ICMS" },
      { name: "pis_cst", label: "CST PIS", type: "dropdown", options: FISCAL_CST_PIS_COFINS_OPTIONS, default: "49", section: "PIS / COFINS" },
      { name: "pis_rate", label: "Aliquota PIS (%)", type: "decimal", default: 0, section: "PIS / COFINS" },
      { name: "cofins_cst", label: "CST COFINS", type: "dropdown", options: FISCAL_CST_PIS_COFINS_OPTIONS, default: "49", section: "PIS / COFINS" },
      { name: "cofins_rate", label: "Aliquota COFINS (%)", type: "decimal", default: 0, section: "PIS / COFINS" },
      { name: "approx_tax_rate", label: "Tributos aprox. (Lei 12.741) (%)", type: "decimal", default: 0, full: true, section: "Outros", hint: "Percentual informado no cupom como tributo aproximado ao consumidor." },
      { name: "is_default", label: "Sugerir como padrao", type: "boolean", default: false, section: "Outros", hint: "Destaca este perfil no cadastro de produtos. Nao altera sozinho a emissao." },
      { name: "is_active", label: "Ativo", type: "boolean", default: true, section: "Outros" },
    ],
  },

  // ── Impressao ──────────────────────────────────────────────────────
  {
    name: "impressoras",
    title: "Impressoras",
    endpoint: "/printers/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "sector_name", label: "Setor" },
      { key: "driver_type", label: "Driver", map: PRINTER_DRIVER_LABELS },
      { key: "connection_type", label: "Conexao", map: PRINTER_CONNECTION_LABELS },
      { key: "endpoint", label: "Dispositivo / porta" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "driver_type", label: "Driver", type: "dropdown", options: PRINTER_DRIVER_OPTIONS, default: "browser" },
      { name: "connection_type", label: "Tipo de conexao", type: "dropdown", options: PRINTER_CONNECTION_OPTIONS, default: "windows", required: true },
      { name: "sector", label: "Setor (opcional)", type: "remote-dropdown", endpoint: "/tables/sectors/", optionLabel: "name", optionValue: "id", placeholder: "Todos os setores" },
      { name: "endpoint", label: "Impressora do Windows ou porta serial", type: "text", placeholder: "Ex.: EPSON TM-T20 ou COM3", hint: "Obrigatorio para conexao Windows/USB ou serial." },
      { name: "host", label: "Endereco IP", type: "text", placeholder: "192.168.1.100", hint: "Obrigatorio para conexao TCP/IP." },
      { name: "port", label: "Porta TCP", type: "number", default: 9100, min: 1 },
      { name: "timeout_seconds", label: "Timeout (segundos)", type: "number", default: 10, min: 1 },
      { name: "auto_print", label: "Imprimir automaticamente", type: "boolean", default: false },
      { name: "settings", label: "Configuracoes avancadas (JSON)", type: "json", default: {}, full: true, rows: 4, hint: "Opcional. Use somente para parametros especificos do equipamento." },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "balancas",
    title: "Balancas",
    endpoint: "/scales/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "sector_name", label: "Setor" },
      { key: "protocol", label: "Protocolo", map: SCALE_PROTOCOL_LABELS },
      { key: "port", label: "Porta" },
      { key: "auto_print", label: "Auto-lancamento", type: "boolean" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "sector", label: "Setor (opcional)", type: "remote-dropdown", endpoint: "/tables/sectors/", optionLabel: "name", optionValue: "id", placeholder: "Todos os setores" },
      { name: "protocol", label: "Protocolo", type: "dropdown", options: SCALE_PROTOCOL_OPTIONS, default: "generic" },
      { name: "port", label: "Porta serial (agente local)", type: "text", placeholder: "COM3 ou /dev/ttyUSB0" },
      { name: "product", label: "Produto por kilo", type: "remote-dropdown", endpoint: "/menu/products/", optionLabel: "name", optionValue: "id", placeholder: "Nenhum produto vinculado" },
      { name: "printer", label: "Impressora da nota de pesagem", type: "remote-dropdown", endpoint: "/printers/", optionLabel: "name", optionValue: "id", placeholder: "Nenhuma impressora vinculada" },
      { name: "reading_max_age_seconds", label: "Validade da leitura (segundos)", type: "number", default: 120 },
      { name: "auto_print", label: "Lancar e imprimir automaticamente ao estabilizar", type: "boolean", default: false },
      { name: "auto_print_delay_seconds", label: "Atraso antes de imprimir (segundos)", type: "number", default: 3 },
      { name: "settings", label: "Configuracoes avancadas (JSON)", type: "json", default: {}, full: true, rows: 4, hint: "Opcional. Parametros adicionais usados pelo agente local." },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },

  // ── Gestao ─────────────────────────────────────────────────────────
  {
    name: "setores",
    title: "Setores",
    endpoint: "/tables/sectors/",
    columns: [
      { key: "name", label: "Setor" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do setor", type: "text", required: true },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "restaurantes",
    title: "Restaurantes",
    endpoint: "/restaurants/",
    globalScope: true,
    pro: {
      // A configuração fiscal (emitente, CSC, certificado, Focus NFe) tem tela
      // própria — é um cadastro à parte, com dados e riscos próprios, e ficava
      // disputando o salvamento com o cadastro do restaurante quando morava
      // dentro dele. Ver views/RestaurantFiscalConfigView.vue.
      rowActions: [
        {
          key: "fiscal",
          label: "Configuração fiscal (Focus NFe)",
          icon: "pi pi-receipt",
          type: "route",
          routeName: "restaurante-fiscal",
          module: "financeiro",
        },
      ],
    },
    columns: [
      { key: "trade_name", label: "Nome fantasia" },
      { key: "legal_name", label: "Razao social" },
      { key: "city", label: "Cidade" },
      { key: "state", label: "UF" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "trade_name", label: "Nome fantasia", type: "text", required: true },
      { name: "legal_name", label: "Razao social", type: "text" },
      { name: "cnpj", label: "CNPJ (opcional)", type: "text", placeholder: "00.000.000/0000-00" },
      { name: "phone", label: "Telefone", type: "text" },
      { name: "email", label: "Email", type: "text", inputType: "email" },
      { name: "address", label: "Endereco", type: "text", full: true },
      { name: "city", label: "Cidade", type: "text" },
      { name: "state", label: "UF", type: "text", placeholder: "SP" },
      { name: "zip_code", label: "CEP", type: "text", placeholder: "00000-000" },
      { name: "default_service_fee_percent", label: "Taxa de servico (%)", type: "decimal", default: 10, section: "Operacao" },
      { name: "require_open_cash_register", label: "Exigir caixa aberto para pagamentos", type: "boolean", default: true, section: "Operacao" },
      // O operador digita a senha comum; a API gera a hash e nunca devolve o valor.
      { name: "cash_action_password", label: "Definir senha de ações do caixa", type: "password", configuredField: "has_cash_action_password", placeholder: "Digite a senha desejada (ex.: 123)", section: "Operacao", full: true, hint: "As bolinhas indicam que já existe uma senha salva. Digite apenas para substituir. Não cole uma hash." },
    ],
  },
  {
    // Terminais (instalações) que já operaram na conta. O cadastro nasce
    // sozinho na primeira operação de cada terminal — esta tela existe para
    // dar nome ao que seria um UUID ("Balcão 01" em vez de "Navegador a1b2c3",
    // que é o que aparece na mensagem de caixa ocupado) e para revogar uma
    // instalação que não deve mais abrir caixa.
    name: "terminais",
    title: "Terminais do PDV",
    endpoint: "/pdv-terminals/",
    globalScope: true,
    module: "base",
    columns: [
      { key: "name", label: "Terminal" },
      { key: "installation_id", label: "Instalacao" },
      { key: "device_type", label: "Tipo", type: "status", map: TERMINAL_TYPE_LABELS },
      { key: "role", label: "Papel", type: "status", map: TERMINAL_ROLE_LABELS },
      { key: "restaurant_name", label: "Restaurante" },
      { key: "last_seen_at", label: "Ultimo contato", type: "date" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do terminal", type: "text", required: true, placeholder: "Balcao 01", full: true, hint: "É este nome que aparece em \"o caixa já está aberto por João no terminal ...\"." },
      { name: "device_type", label: "Tipo", type: "dropdown", options: TERMINAL_TYPE_OPTIONS },
      { name: "role", label: "Papel na rede local", type: "dropdown", options: TERMINAL_ROLE_OPTIONS },
      { name: "restaurant", label: "Restaurante", type: "remote-dropdown", endpoint: "/restaurants/", optionLabel: "trade_name", optionValue: "id", placeholder: "Todos os restaurantes", globalScope: true },
      { name: "is_active", label: "Ativo", type: "boolean", default: true, hint: "Desative para impedir que esta instalação volte a abrir caixa." },
      { name: "revoked_reason", label: "Motivo da revogacao", type: "textarea", full: true, section: "Revogacao" },
    ],
  },
  {
    name: "usuarios",
    title: "Usuarios",
    endpoint: "/users/",
    globalScope: true,
    columns: [
      { key: "username", label: "Usuario" },
      { key: "email", label: "Email" },
      { key: "first_name", label: "Nome" },
      { key: "profile.profile_type", label: "Perfil", type: "status", map: PROFILE_TYPE_LABELS },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "username", label: "Nome de usuario", type: "text", required: true, section: "Acesso" },
      { name: "email", label: "Email", type: "text", inputType: "email", required: true, section: "Acesso" },
      { name: "password", label: "Senha", type: "password", section: "Acesso" },
      { name: "first_name", label: "Nome", type: "text", section: "Identificação" },
      { name: "last_name", label: "Sobrenome", type: "text", section: "Identificação" },
      { name: "profile.phone", label: "Telefone", type: "text", placeholder: "(11) 90000-0000", section: "Identificação" },
      // Perfil (UserProfile) — enviado aninhado como `profile.*`.
      { name: "profile.profile_type", label: "Perfil de acesso", type: "dropdown", options: PROFILE_TYPE_OPTIONS, default: "waiter", required: true, section: "Perfil de acesso" },
      { name: "profile.restaurant", label: "Restaurante", type: "remote-dropdown", endpoint: "/restaurants/", optionLabel: "trade_name", optionValue: "id", placeholder: "Todos os restaurantes", globalScope: true, section: "Perfil de acesso" },
      { name: "profile.role", label: "Cargo / permissões", type: "remote-dropdown", endpoint: "/roles/", optionLabel: "name", optionValue: "id", placeholder: "Sem cargo específico", globalScope: true, section: "Perfil de acesso" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true, section: "Perfil de acesso" },
    ],
  },
  {
    // Perfis fixos (Garçom, Caixa, Gerente, Administrador) — ver backend
    // apps/accounts/role_catalog.py. Sem `formFields`: tela somente-leitura,
    // não há mais opção de criar/editar/apagar perfil (API também bloqueia).
    name: "perfis",
    title: "Perfis de Acesso",
    endpoint: "/roles/",
    globalScope: true,
    columns: [
      { key: "name", label: "Perfil" },
      { key: "code", label: "Codigo" },
      { key: "is_account_admin", label: "Admin da conta", type: "boolean" },
      { key: "max_discount_percent", label: "Desconto max. (%)" },
      { key: "created_at", label: "Criado em", type: "date" },
    ],
  },
];
