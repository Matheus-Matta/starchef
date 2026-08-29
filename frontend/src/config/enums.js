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

// ── Perfil fiscal (grupo tributario reutilizado pelos produtos) ─────────────
// Tabelas oficiais da NF-e/NFC-e; os codigos vao literalmente para a Focus NFe.
// Origem da mercadoria (campo `orig` do ICMS).
export const FISCAL_ORIGEM_OPTIONS = [
  { label: "0 - Nacional", value: "0" },
  { label: "1 - Estrangeira (importacao direta)", value: "1" },
  { label: "2 - Estrangeira (mercado interno)", value: "2" },
  { label: "3 - Nacional com importacao > 40%", value: "3" },
  { label: "4 - Nacional (processos produtivos basicos)", value: "4" },
  { label: "5 - Nacional com importacao <= 40%", value: "5" },
  { label: "6 - Estrangeira (importacao direta, sem similar)", value: "6" },
  { label: "7 - Estrangeira (mercado interno, sem similar)", value: "7" },
  { label: "8 - Nacional com importacao > 70%", value: "8" },
];
// CSOSN — usado por quem e do Simples Nacional (CRT 1 ou 2).
export const FISCAL_CSOSN_OPTIONS = [
  { label: "101 - Tributada com permissao de credito", value: "101" },
  { label: "102 - Tributada sem permissao de credito", value: "102" },
  { label: "103 - Isencao do ICMS para faixa de receita", value: "103" },
  { label: "300 - Imune", value: "300" },
  { label: "400 - Nao tributada", value: "400" },
  { label: "500 - ICMS cobrado por substituicao tributaria", value: "500" },
  { label: "900 - Outros", value: "900" },
];
// CST do ICMS — usado por quem e do Regime Normal (CRT 3).
export const FISCAL_CST_ICMS_OPTIONS = [
  { label: "00 - Tributada integralmente", value: "00" },
  { label: "10 - Tributada com cobranca por ST", value: "10" },
  { label: "20 - Com reducao de base de calculo", value: "20" },
  { label: "40 - Isenta", value: "40" },
  { label: "41 - Nao tributada", value: "41" },
  { label: "50 - Suspensao", value: "50" },
  { label: "51 - Diferimento", value: "51" },
  { label: "60 - ICMS cobrado anteriormente por ST", value: "60" },
  { label: "90 - Outras", value: "90" },
];
// CST de PIS/COFINS — a mesma tabela vale para os dois tributos.
export const FISCAL_CST_PIS_COFINS_OPTIONS = [
  { label: "01 - Operacao tributavel (aliquota basica)", value: "01" },
  { label: "02 - Operacao tributavel (aliquota diferenciada)", value: "02" },
  { label: "04 - Monofasica (aliquota zero)", value: "04" },
  { label: "06 - Aliquota zero", value: "06" },
  { label: "07 - Operacao isenta", value: "07" },
  { label: "08 - Operacao sem incidencia", value: "08" },
  { label: "09 - Operacao com suspensao", value: "09" },
  { label: "49 - Outras operacoes de saida", value: "49" },
  { label: "99 - Outras operacoes", value: "99" },
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

// ── Terminais do PDV ────────────────────────────────────────────────────────
// A instalação é identificada por um UUID; estes rótulos existem para a tela
// não mostrar o UUID cru quando disser quem está com um caixa.
export const TERMINAL_TYPE_OPTIONS = [
  { label: "Desktop", value: "desktop" },
  { label: "Navegador", value: "web" },
  { label: "Aplicativo", value: "mobile" },
];
export const TERMINAL_TYPE_LABELS = Object.fromEntries(
  TERMINAL_TYPE_OPTIONS.map((option) => [option.value, option.label]),
);
export const TERMINAL_ROLE_OPTIONS = [
  { label: "Caixa Principal", value: "principal" },
  { label: "Caixa Secundario", value: "secondary" },
  { label: "Navegador", value: "web" },
];
export const TERMINAL_ROLE_LABELS = Object.fromEntries(
  TERMINAL_ROLE_OPTIONS.map((option) => [option.value, option.label]),
);
