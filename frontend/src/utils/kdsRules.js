export const ACTIONS = { include: "Incluir", exclude: "Excluir", move: "Mover" };

export const FIELDS = [
  { value: "order_type", label: "Tipo do pedido" },
  { value: "production_sector", label: "Setor de produção" },
  { value: "item_status", label: "Status do item" },
  { value: "order_status", label: "Status do pedido" },
  { value: "payment_status", label: "Status do pagamento" },
  { value: "production_status", label: "Status da produção" },
  { value: "delivery_status", label: "Status da entrega" },
  { value: "minutes_since_sent", label: "Minutos desde o envio" },
  { value: "minutes_in_column", label: "Minutos na coluna atual" },
  { value: "has_customer_note", label: "Tem observação" },
  { value: "has_table", label: "Tem mesa" },
  { value: "has_command", label: "Tem comanda" },
  { value: "column_is_entry", label: "Está na coluna de entrada" },
];

const text = [
  { value: "equals", label: "É igual a" }, { value: "not_equals", label: "É diferente de" },
];
export const OPERATORS = {
  text,
  number: [{ value: "gte", label: "Maior ou igual" }, { value: "lte", label: "Menor ou igual" }, ...text],
  boolean: [{ value: "true", label: "Sim" }, { value: "false", label: "Não" }],
};

const VALUES = {
  order_type: [["command", "Comanda"], ["counter", "Balcão"], ["delivery", "Delivery"], ["takeaway", "Retirada"], ["internal", "Interno"]],
  production_sector: [["kitchen", "Cozinha"], ["bar", "Bar"], ["dessert", "Sobremesas"]],
  item_status: [["sent", "Novo"], ["preparing", "Em preparo"], ["ready", "Pronto"], ["cancelled", "Cancelado"]],
  order_status: [["open", "Aberto"], ["awaiting_payment", "Aguardando pagamento"], ["paid", "Pago"], ["cancelled", "Cancelado"], ["refunded", "Estornado"]],
  payment_status: [["pending", "Pendente"], ["partial", "Parcial"], ["paid", "Pago"], ["refunded", "Estornado"], ["cancelled", "Cancelado"]],
  production_status: [["sent_to_kitchen", "Enviado"], ["preparing", "Em preparo"], ["partially_ready", "Parcialmente pronto"], ["ready", "Pronto"], ["delivered", "Entregue"]],
  delivery_status: [["pending", "Pendente"], ["out_for_delivery", "Saiu para entrega"], ["delivered", "Entregue"], ["failed", "Falhou"]],
};
export function fieldValues(field) { return (VALUES[field] || []).map(([value, label]) => ({ value, label })); }

export function ruleSummary(rule, columns) {
  const action = ACTIONS[rule.action] || rule.action;
  const target = columns.find((column) => column.id === rule.target_column)?.name;
  const conditions = rule.conditions || [];
  if (!conditions.length) return `${action}${target ? ` para ${target}` : ""} · sempre`;
  const textSummary = conditions.map((condition) => {
    const field = FIELDS.find((entry) => entry.value === condition.field)?.label || condition.field;
    const value = fieldValues(condition.field).find((entry) => entry.value === condition.value)?.label ?? condition.value ?? "";
    return `${field} ${value}`.trim();
  }).join(rule.match === "any" ? " ou " : " e ");
  return `${action}${target ? ` para ${target}` : ""} · ${textSummary}`;
}
