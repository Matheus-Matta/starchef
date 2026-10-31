// Rótulos do domínio de estoque. Os valores à esquerda são o contrato da API;
// os textos à direita são sempre o que o operador deve enxergar.
export const STOCK_DOC_STATUS_LABELS = {
  draft: "Rascunho", posted: "Confirmado", cancelled: "Cancelado",
};

export const STOCK_LOT_STATUS_LABELS = {
  available: "Disponível", depleted: "Esgotado", blocked: "Bloqueado",
  expired: "Vencido", discarded: "Descartado",
};

export const STOCK_EXIT_TYPE_LABELS = {
  consumption: "Consumo manual", loss: "Perda", discard: "Descarte",
  transfer: "Transferência", internal: "Uso interno", other: "Outro",
};
export const STOCK_EXIT_TYPE_OPTIONS = Object.entries(STOCK_EXIT_TYPE_LABELS)
  .map(([value, label]) => ({ value, label }));

export const STOCK_PICKING_LABELS = {
  fifo: "FIFO — primeiro a entrar, primeiro a sair",
  fefo: "FEFO — primeiro a vencer, primeiro a sair",
};
export const STOCK_PICKING_OPTIONS = Object.entries(STOCK_PICKING_LABELS)
  .map(([value, label]) => ({ value, label }));

export const LABEL_CODE_TYPE_LABELS = {
  qr: "QR Code", code128: "Código de barras (Code 128)",
};
export const LABEL_CODE_TYPE_OPTIONS = Object.entries(LABEL_CODE_TYPE_LABELS)
  .map(([value, label]) => ({ value, label }));

export const INBOUND_NFE_STATUS_LABELS = {
  pending_mapping: { label: "Pendente de Vínculo", tone: "warning" },
  pending_receipt: { label: "Pronta para Entrada", tone: "info" },
  received: { label: "Entrada Concluída", tone: "success" },
  ignored: { label: "Ignorada", tone: "neutral" },
  summary: { label: "Resumo SEFAZ", tone: "neutral" },
  xml_available: { label: "XML Completo", tone: "info" },
  cancelled: { label: "Cancelada", tone: "danger" },
  PENDING: { label: "Pendente de Vínculo", tone: "warning" },
  MANIFESTED: { label: "Manifestada", tone: "info" },
  STOCKED: { label: "Entrada Concluída", tone: "success" },
  IGNORED: { label: "Ignorada", tone: "neutral" },
  CANCELED: { label: "Cancelada", tone: "danger" },
  CANCELLED: { label: "Cancelada", tone: "danger" },
};

export const ASSET_STATUS_LABELS = {
  IN_USE: { label: "Em uso", tone: "success" },
  IN_STOCK: { label: "Disponível / estoque", tone: "info" },
  IN_MAINTENANCE: { label: "Em manutenção", tone: "warning" },
  BROKEN: { label: "Com avaria", tone: "danger" },
  LOANED: { label: "Emprestado", tone: "neutral" },
  TRANSFERRED: { label: "Transferido", tone: "neutral" },
  INACTIVE: { label: "Desativado", tone: "neutral" },
  DISPOSED: { label: "Baixado", tone: "danger" },
  LOST: { label: "Extraviado", tone: "danger" },
  STOLEN: { label: "Furtado / roubado", tone: "danger" },
  in_use: { label: "Em uso", tone: "success" },
  in_maintenance: { label: "Em manutenção", tone: "warning" },
  idle: { label: "Disponível", tone: "info" },
  disposed: { label: "Baixado", tone: "danger" },
};

export const ASSET_STATUS_OPTIONS = [
  { label: "Em uso / operação", value: "IN_USE" },
  { label: "Disponível / em estoque", value: "IN_STOCK" },
  { label: "Em manutenção", value: "IN_MAINTENANCE" },
  { label: "Com avaria / inoperante", value: "BROKEN" },
  { label: "Emprestado / comodato", value: "LOANED" },
  { label: "Transferido", value: "TRANSFERRED" },
  { label: "Desativado", value: "INACTIVE" },
  { label: "Baixado / descartado", value: "DISPOSED" },
  { label: "Extraviado", value: "LOST" },
  { label: "Furtado / roubado", value: "STOLEN" },
];

export const INVENTORY_LOT_STATUS_LABELS = {
  ACTIVE: { label: "Ativo / Disponível", tone: "success" },
  CONSUMED: { label: "Esgotado", tone: "neutral" },
  EXPIRED: { label: "Vencido", tone: "danger" },
  BLOCKED: { label: "Bloqueado / Quarentena", tone: "warning" },
  DISCARDED: { label: "Descartado", tone: "danger" },
  active: { label: "Ativo / Disponível", tone: "success" },
  depleted: { label: "Esgotado", tone: "neutral" },
  expired: { label: "Vencido", tone: "danger" },
  quarantine: { label: "Bloqueado / Quarentena", tone: "warning" },
};

export const GOODS_RECEIPT_STATUS_LABELS = {
  DRAFT: { label: "Em conferência", tone: "neutral" },
  CONFIRMED: { label: "Confirmado", tone: "success" },
  DIVERGENT: { label: "Confirmado com divergência", tone: "warning" },
  CANCELLED: { label: "Cancelado", tone: "danger" },
  draft: { label: "Em conferência", tone: "neutral" },
  received: { label: "Confirmado", tone: "success" },
  divergent: { label: "Confirmado com divergência", tone: "warning" },
  rejected: { label: "Rejeitado", tone: "danger" },
};

export const ITEM_TYPE_OPTIONS = [
  { label: "Mercadoria para revenda", value: "RESALE_PRODUCT" },
  { label: "Insumo / matéria-prima", value: "INGREDIENT" },
  { label: "Material de consumo", value: "CONSUMABLE" },
  { label: "Material reutilizável (utensílios)", value: "REUSABLE_MATERIAL" },
  { label: "Equipamento operacional", value: "EQUIPMENT" },
  { label: "Ativo fixo / patrimônio", value: "FIXED_ASSET" },
  { label: "Embalagem", value: "PACKAGING" },
  { label: "Serviço", value: "SERVICE" },
  { label: "Outro", value: "OTHER" },
];

export const TRACKING_MODE_OPTIONS = [
  { label: "Apenas quantidade / saldo", value: "QUANTITY" },
  { label: "Lote e validade (FEFO)", value: "LOT" },
  { label: "Serializado / patrimônio individual", value: "SERIALIZED" },
];
