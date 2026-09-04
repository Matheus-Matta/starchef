/**
 * Fonte unica de verdade para rotulos de status e listas de opcoes.
 * Reaproveitado pelas colunas das listas, pelos formularios e pelas telas de detalhe.
 *
 * Convencao:
 *  - `*_LABELS`  -> mapa { valorDoBackend: rotuloExibido } para status/enums.
 *  - `*_OPTIONS` -> array [{ label, value }] para dropdowns de formulario/filtro.
 */

/* ── Mapas de rotulo (valor do backend -> texto) ─────────────────────── */
export const ORDER_TYPE_LABELS = {
  command: "Comanda",
  counter: "Balcao",
  delivery: "Delivery",
  takeaway: "Retirada",
  internal: "Interno",
};

export const ORDER_STATUS_LABELS = {
  open: "Aberto",
  sent_to_kitchen: "Cozinha",
  preparing: "Preparo",
  partially_ready: "Parcial",
  ready: "Pronto",
  delivered: "Entregue",
  awaiting_payment: "Pagamento",
  paid: "Pago",
  cancelled: "Cancelado",
  refunded: "Estornado",
};

// Status de preparação (cozinha) — Order.production_status.
export const PRODUCTION_STATUS_LABELS = {
  idle: "Aguardando",
  sent_to_kitchen: "Na cozinha",
  preparing: "Preparando",
  partially_ready: "Parcial",
  ready: "Pronto",
  delivered: "Entregue",
};

// Status de pagamento — Order.payment_status.
export const PAYMENT_STATUS_LABELS = {
  pending: "Pendente",
  partial: "Parcial",
  paid: "Pago",
  refunded: "Estornado",
};

// Status de entrega — Order.delivery_status (só com módulo de entrega).
export const DELIVERY_STATUS_LABELS = {
  pending: "Aguardando",
  out_for_delivery: "A caminho",
  delivered: "Entregue",
  failed: "Falhou",
};

export const TABLE_STATUS_LABELS = {
  free: "Livre",
  occupied: "Ocupada",
  reserved: "Reservada",
  cleaning: "Limpeza",
};

// Status da comanda reutilizavel — Command.status.
export const COMMAND_STATUS_LABELS = {
  free: "Livre",
  occupied: "Em uso",
};

export const PROFILE_TYPE_LABELS = {
  admin: "Admin",
  owner: "Proprietario",
  manager: "Gerente",
  waiter: "Garcom",
  kitchen: "Cozinha",
  cashier: "Caixa",
  driver: "Entregador",
};

export const PROFILE_TYPE_OPTIONS = Object.entries(PROFILE_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

export const MOVEMENT_TYPE_LABELS = {
  in: "Entrada",
  out: "Saida",
  adjustment: "Ajuste",
  sale: "Venda",
  inventory: "Inventario",
};

export const VEHICLE_TYPE_LABELS = {
  bike: "Bicicleta",
  motorcycle: "Moto",
  car: "Carro",
  foot: "A pe",
};

export const MENU_CHANNEL_LABELS = {
  all: "Todos",
  table: "Salao",
  delivery: "Delivery",
  counter: "Balcao",
  digital: "Digital",
};

export const CASH_STATUS_LABELS = { open: "Aberto", closed: "Fechado" };

export const INVOICE_STATUS_LABELS = {
  draft: "Rascunho",
  pending: "Aguardando autorizacao",
  issued: "Emitida",
  cancelled: "Cancelada",
  error: "Erro",
};

export const EMISSION_TYPE_LABELS = { "1": "Normal", "9": "Contingencia" };

// Espelham FiscalConfig.* do backend (apps/invoices/models.py).
export const FISCAL_DOCUMENT_MODEL_OPTIONS = [
  { label: "NFC-e (modelo 65)", value: "65" },
  { label: "NF-e (modelo 55)", value: "55" },
  { label: "SAT/CF-e (modelo 59)", value: "59" },
];
export const FISCAL_ENVIRONMENT_OPTIONS = [
  { label: "Homologacao", value: "2" },
  { label: "Producao", value: "1" },
];
export const FISCAL_CRT_OPTIONS = [
  { label: "Simples Nacional", value: "1" },
  { label: "Simples Nacional - excesso de sublimite", value: "2" },
  { label: "Regime Normal", value: "3" },
];
// "manual" = scaffold (nao transmite a SEFAZ, so monta o documento). Outros
// provedores precisam ser registrados no backend (apps/invoices/providers.py)
// antes de aparecerem aqui como opcao utilizavel de verdade.
export const FISCAL_PROVIDER_OPTIONS = [
  { label: "Manual (sem transmissao a SEFAZ)", value: "manual" },
  { label: "Focus NFe", value: "focus_nfe" },
];

export const STOCK_TIMING_LABELS = { payment: "No pagamento", kitchen: "Na cozinha" };

// Espelham PaymentMethod.TYPE_CHOICES / Printer.DRIVER_CHOICES do backend.
export const PAYMENT_METHOD_TYPE_LABELS = { cash: "Dinheiro", card: "Cartao", pix: "PIX", voucher: "Voucher", other: "Outro" };
export const PRINTER_DRIVER_LABELS = { browser: "Navegador", escpos: "ESC/POS" };
export const PRINTER_CONNECTION_OPTIONS = [
  { label: "Windows / USB", value: "windows" },
  { label: "Rede TCP/IP", value: "network" },
  { label: "Porta serial", value: "serial" },
];
export const PRINTER_CONNECTION_LABELS = Object.fromEntries(PRINTER_CONNECTION_OPTIONS.map((o) => [o.value, o.label]));

/* ── Listas de opcoes para formularios ───────────────────────────────── */
export const SECTOR_OPTIONS = [
  { label: "Cozinha", value: "kitchen" },
  { label: "Bar", value: "bar" },
  { label: "Sobremesa", value: "dessert" },
];

// Espelha Ingredient.UNIT_CHOICES do backend (valores exatos — nao inventar novos).
export const UNIT_OPTIONS = [
  { label: "Unidade", value: "unit" },
  { label: "kg", value: "kg" },
  { label: "g", value: "g" },
  { label: "L", value: "l" },
  { label: "ml", value: "ml" },
];

export const CHANNEL_OPTIONS = [
  { label: "Todos", value: "all" },
  { label: "Salao", value: "table" },
  { label: "Delivery", value: "delivery" },
  { label: "Balcao", value: "counter" },
  { label: "Digital", value: "digital" },
];

export const VEHICLE_OPTIONS = [
  { label: "Bicicleta", value: "bike" },
  { label: "Moto", value: "motorcycle" },
  { label: "Carro", value: "car" },
  { label: "A pe", value: "foot" },
];

// Espelha PaymentMethod.TYPE_CHOICES do backend (so existe UM tipo "card", sem credito/debito separados).
export const PAYMENT_TYPE_OPTIONS = [
  { label: "Dinheiro", value: "cash" },
  { label: "Cartao", value: "card" },
  { label: "PIX", value: "pix" },
  { label: "Voucher Refeicao", value: "voucher" },
  { label: "Outro", value: "other" },
];

// Espelha ServiceLevelAgreement.TYPE_CHOICES / PRIORITY_CHOICES do backend (SLA).
export const SLA_TYPE_OPTIONS = [
  { label: "Atendimento", value: "service" },
  { label: "Preparo", value: "prep" },
  { label: "Entrega", value: "delivery" },
  { label: "Retirada", value: "pickup" },
  { label: "Outro", value: "other" },
];
export const SLA_TYPE_LABELS = Object.fromEntries(SLA_TYPE_OPTIONS.map((o) => [o.value, o.label]));

export const SLA_PRIORITY_OPTIONS = [
  { label: "Baixa", value: "low" },
  { label: "Normal", value: "normal" },
  { label: "Alta", value: "high" },
  { label: "Urgente", value: "urgent" },
];
export const SLA_PRIORITY_LABELS = Object.fromEntries(SLA_PRIORITY_OPTIONS.map((o) => [o.value, o.label]));

// Espelha Printer.DRIVER_CHOICES do backend.
export const PRINTER_DRIVER_OPTIONS = [
  { label: "Navegador", value: "browser" },
  { label: "ESC/POS (termica)", value: "escpos" },
];

// Espelha Scale.PROTOCOL_CHOICES do backend.
export const SCALE_PROTOCOL_OPTIONS = [
  { label: "Generico", value: "generic" },
  { label: "Toledo PRT2", value: "toledo_prt2" },
  { label: "Filizola", value: "filizola" },
  { label: "Urano", value: "urano" },
];
export const SCALE_PROTOCOL_LABELS = { generic: "Generico", toledo_prt2: "Toledo PRT2", filizola: "Filizola", urano: "Urano" };

export const STOCK_TIMING_OPTIONS = [
  { label: "No pagamento", value: "payment" },
  { label: "Na cozinha", value: "kitchen" },
];

export const PRODUCT_TYPE_OPTIONS = [
  { label: "Prato", value: "meal" },
  { label: "Bebida", value: "drink" },
  { label: "Sobremesa", value: "dessert" },
  { label: "Combo", value: "combo" },
  { label: "Adicional", value: "addon" },
  { label: "Insumo", value: "input" },
];

export const PRICING_OPTIONS = [
  { label: "Por unidade", value: "unit" },
  { label: "Por kilo", value: "kg" },
];

/* ── Listas de opcoes de FILTRO (incluem a opcao "Todos") ────────────── */
export const ACTIVE_FILTER_OPTIONS = [
  { label: "Todos", value: "all" },
  { label: "Ativos", value: true },
  { label: "Inativos", value: false },
];

export const PRODUCT_TYPE_FILTER_OPTIONS = [
  { label: "Todos os tipos", value: "all" },
  { label: "Pratos", value: "meal" },
  { label: "Bebidas", value: "drink" },
  { label: "Sobremesas", value: "dessert" },
  { label: "Combos", value: "combo" },
  { label: "Adicionais", value: "addon" },
];

export const SECTOR_FILTER_OPTIONS = [
  { label: "Todos os setores", value: "all" },
  { label: "Cozinha", value: "kitchen" },
  { label: "Bar", value: "bar" },
  { label: "Sobremesa", value: "dessert" },
];

export const INBOUND_NFE_STATUS_LABELS = {
  pending_mapping: { label: "Pendente de Vínculo", tone: "warning" },
  pending_receipt: { label: "Pronta p/ Entrada", tone: "info" },
  received: { label: "Entrada Concluída", tone: "success" },
  summary: { label: "Resumo SEFAZ", tone: "neutral" },
  xml_available: { label: "XML Completo", tone: "info" },
  cancelled: { label: "Cancelada", tone: "danger" },
  // Compatibilidade
  PENDING: { label: "Pendente de Vínculo", tone: "warning" },
  MANIFESTED: { label: "Manifestada", tone: "info" },
  STOCKED: { label: "Entrada Concluída", tone: "success" },
  CANCELED: { label: "Cancelada", tone: "danger" },
};

export const ASSET_STATUS_LABELS = {
  IN_USE: { label: "Em Uso", tone: "success" },
  IN_STOCK: { label: "Disponível / Estoque", tone: "info" },
  IN_MAINTENANCE: { label: "Em Manutenção", tone: "warning" },
  BROKEN: { label: "Com Avaria", tone: "danger" },
  LOANED: { label: "Emprestado", tone: "neutral" },
  TRANSFERRED: { label: "Transferido", tone: "neutral" },
  INACTIVE: { label: "Desativado", tone: "neutral" },
  DISPOSED: { label: "Baixado", tone: "danger" },
  LOST: { label: "Extraviado", tone: "danger" },
  STOLEN: { label: "Furtado / Roubado", tone: "danger" },
  // Compatibilidade com minúsculas legadas
  in_use: { label: "Em Uso", tone: "success" },
  in_maintenance: { label: "Em Manutenção", tone: "warning" },
  idle: { label: "Disponível", tone: "info" },
  disposed: { label: "Baixado", tone: "danger" },
};

export const ASSET_STATUS_OPTIONS = [
  { label: "Em Uso / Operação", value: "IN_USE" },
  { label: "Disponível / Em Estoque", value: "IN_STOCK" },
  { label: "Em Manutenção", value: "IN_MAINTENANCE" },
  { label: "Com Avaria / Inoperante", value: "BROKEN" },
  { label: "Emprestado / Comodato", value: "LOANED" },
  { label: "Transferido", value: "TRANSFERRED" },
  { label: "Desativado", value: "INACTIVE" },
  { label: "Baixado / Descartado", value: "DISPOSED" },
  { label: "Extraviado", value: "LOST" },
  { label: "Furtado / Roubado", value: "STOLEN" },
];

export const INVENTORY_LOT_STATUS_LABELS = {
  active: { label: "Ativo", tone: "success" },
  depleted: { label: "Esgotado", tone: "neutral" },
  expired: { label: "Vencido", tone: "danger" },
  quarantine: { label: "Quarentena", tone: "warning" },
};

export const GOODS_RECEIPT_STATUS_LABELS = {
  draft: { label: "Rascunho", tone: "neutral" },
  received: { label: "Conforme", tone: "success" },
  divergent: { label: "Com Divergência", tone: "warning" },
  rejected: { label: "Rejeitado", tone: "danger" },
};

export const ITEM_TYPE_OPTIONS = [
  { label: "Mercadoria para Revenda", value: "RESALE_PRODUCT" },
  { label: "Insumo / Matéria-Prima", value: "INGREDIENT" },
  { label: "Material de Consumo", value: "CONSUMABLE" },
  { label: "Material Reutilizável (Utensílios)", value: "REUSABLE_MATERIAL" },
  { label: "Equipamento Operacional", value: "EQUIPMENT" },
  { label: "Ativo Fixo / Patrimônio", value: "FIXED_ASSET" },
  { label: "Embalagem", value: "PACKAGING" },
  { label: "Serviço", value: "SERVICE" },
  { label: "Outro", value: "OTHER" },
];

export const TRACKING_MODE_OPTIONS = [
  { label: "Apenas Quantidade / Saldo", value: "QUANTITY" },
  { label: "Lote e Validade (FEFO)", value: "LOT" },
  { label: "Serializado / Patrimônio Individual", value: "SERIALIZED" },
];
