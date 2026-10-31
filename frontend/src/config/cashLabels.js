export const CASH_MOVEMENT_TYPE_LABELS = {
  opening: "Abertura",
  sale: "Venda em dinheiro",
  withdrawal: "Sangria",
  supply: "Suprimento",
  closing: "Fechamento",
  adjustment: "Ajuste",
  refund: "Estorno",
};

export const CASH_MOVEMENT_STATUS_LABELS = {
  pending: "Pendente",
  approved: "Confirmada",
  cancelled: "Cancelada",
};

export const CASH_AUTHORIZATION_LABELS = {
  pending: "Pendente",
  cash_password: "Senha do caixa",
  manager: "Gerente",
  automatic: "Automática",
};

export const PAYMENT_DETAIL_LABELS = {
  cash: "Dinheiro",
  card: "Cartão",
  pix: "PIX",
  voucher: "Voucher",
  other: "Outro",
  credit: "Crédito",
  debit: "Débito",
};

export const ORDER_ITEM_STATUS_LABELS = {
  pending: "Pendente",
  queued: "Na fila",
  sent: "Enviado",
  preparing: "Em preparo",
  ready: "Pronto",
  delivered: "Entregue",
  cancelled: "Cancelado",
  comped: "Cortesia",
};

export const CASH_STATUS_TONES = {
  pending_opening: "warning",
  open: "success",
  blocked: "danger",
  pending_manager_approval: "warning",
  pending_closing: "warning",
  closed: "info",
  closed_with_difference: "warning",
  cancelled: "danger",
};
