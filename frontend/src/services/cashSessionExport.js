const TYPES = {
  opening: "Abertura",
  sale: "Venda em dinheiro",
  withdrawal: "Sangria",
  supply: "Suprimento",
  closing: "Fechamento",
  adjustment: "Ajuste",
  refund: "Estorno",
};

function cell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function add(rows, values = []) {
  rows.push(values.map(cell).join(";"));
}

export function downloadCashSessionCsv(statement) {
  const session = statement.session || {};
  const rows = [];
  add(rows, ["StarChef — Extrato completo da sessão de caixa"]);
  add(rows, ["Sessão", session.id]);
  add(rows, ["Caixa", session.cash_station_name]);
  add(rows, ["Operador", session.opened_by_name]);
  add(rows, ["Terminal", session.terminal_label]);
  add(rows, ["Fechado por", session.closed_by_name]);
  add(rows, ["Terminal de fechamento", session.closed_terminal_label]);
  add(rows, ["Abertura", session.opened_at]);
  add(rows, ["Fechamento", session.closed_at]);
  add(rows, ["Status", session.status]);
  add(rows, ["Valor de abertura", session.opening_amount]);
  add(rows, ["Esperado", session.expected_amount]);
  add(rows, ["Contado", session.actual_amount]);
  add(rows, ["Diferença", session.difference_amount]);
  add(rows);
  add(rows, ["Movimentações"]);
  add(rows, ["Data", "Tipo", "Valor", "Saldo após", "Status", "Motivo", "Destino/origem", "Operador", "Terminal", "Autorização", "Autorizado por", "Pedido", "Forma"]);
  for (const movement of session.movements || []) {
    add(rows, [movement.created_at, TYPES[movement.movement_type] || movement.movement_type, movement.amount, movement.balance_after, movement.status, movement.reason, movement.destination, movement.operator_name, movement.terminal_label, movement.authorization, movement.authorized_by_name, movement.order_sequence, movement.payment_method_name]);
  }
  add(rows);
  add(rows, ["Recebimentos"]);
  add(rows, ["Data", "Pedido", "Forma", "Tipo", "Valor", "Troco"]);
  for (const sale of session.sales || []) {
    add(rows, [sale.paid_at, sale.order_sequence, sale.payment_method_name, sale.card_subtype || sale.method_type, sale.amount, sale.change_amount]);
  }
  add(rows);
  add(rows, ["Pedidos"]);
  add(rows, ["Pedido", "Referência", "Tipo", "Abertura", "Fechamento", "Operador", "Fechado por", "Status", "Pagamento", "Subtotal", "Serviço", "Desconto", "Entrega", "Total", "Observações", "Falha/cancelamento"]);
  for (const order of statement.orders || []) {
    add(rows, [order.sequence, order.reference, order.order_type, order.opened_at, order.closed_at, order.operator_name, order.closed_by_name, order.status, order.payment_status, order.subtotal, order.service_fee, order.discount, order.delivery_fee, order.total, order.notes, order.cancel_reason]);
  }
  add(rows);
  add(rows, ["Itens vendidos"]);
  add(rows, ["Pedido", "Referência", "Produto", "Quantidade", "Unitário", "Total", "Status", "Setor", "Variações", "Adicionais", "Observação", "Falha/cancelamento"]);
  for (const order of statement.orders || []) {
    for (const item of order.items || []) {
      add(rows, [order.sequence, order.reference, item.product_name, item.quantity, item.unit_price, item.total_price, item.status, item.production_sector, JSON.stringify(item.variations || {}), (item.addons || []).map((addon) => `${addon.quantity}x ${addon.name}`).join(" | "), item.customer_note, item.void_reason]);
    }
  }

  const blob = new Blob(["\ufeff", rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `sessao_caixa_${String(session.id || "detalhe").slice(0, 8)}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[char]);
}

function table(headers, rows) {
  return `<table><thead><tr>${headers.map((value) => `<th>${escapeHtml(value)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((value) => `<td>${escapeHtml(value)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

export function printCashSessionStatement(statement) {
  const session = statement.session || {};
  const movementRows = (session.movements || []).map((item) => [item.created_at, TYPES[item.movement_type] || item.movement_type, item.amount, item.balance_after, item.status, item.reason, item.destination, item.operator_name, item.terminal_label]);
  const saleRows = (session.sales || []).map((item) => [item.paid_at, `#${item.order_sequence}`, item.payment_method_name, item.card_subtype || item.method_type, item.amount, item.change_amount]);
  const orderRows = (statement.orders || []).map((order) => [`#${order.sequence}`, order.reference, order.order_type, order.opened_at, order.closed_at, order.operator_name, order.closed_by_name, order.status, order.payment_status, order.subtotal, order.service_fee, order.discount, order.delivery_fee, order.total, order.notes || order.cancel_reason]);
  const itemRows = (statement.orders || []).flatMap((order) => (order.items || []).map((item) => [`#${order.sequence}`, order.reference, item.product_name, item.quantity, item.unit_price, item.total_price, item.status, JSON.stringify(item.variations || {}), (item.addons || []).map((addon) => `${addon.quantity}x ${addon.name}`).join(" | "), item.customer_note || item.void_reason]));
  const popup = window.open("", "_blank");
  if (!popup) return false;
  popup.opener = null;
  popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Extrato do caixa</title><style>body{font:12px Arial;color:#111;margin:24px}h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px}p{margin:3px 0}table{width:100%;border-collapse:collapse;margin-bottom:16px}th,td{padding:6px;border:1px solid #bbb;text-align:left}th{background:#eee}@page{size:landscape;margin:12mm}</style></head><body><h1>Extrato da sessão de caixa</h1><p><b>Caixa:</b> ${escapeHtml(session.cash_station_name)}</p><p><b>Operador:</b> ${escapeHtml(session.opened_by_name)} · <b>Terminal:</b> ${escapeHtml(session.terminal_label)}</p><p><b>Abertura:</b> ${escapeHtml(session.opened_at)} · <b>Fechamento:</b> ${escapeHtml(session.closed_at || "Em andamento")}</p><p><b>Fechado por:</b> ${escapeHtml(session.closed_by_name)} · <b>Terminal:</b> ${escapeHtml(session.closed_terminal_label)}</p><p><b>Esperado:</b> ${escapeHtml(session.expected_amount)} · <b>Contado:</b> ${escapeHtml(session.actual_amount)} · <b>Diferença:</b> ${escapeHtml(session.difference_amount)}</p><h2>Entradas, saídas e suprimentos</h2>${table(["Data", "Movimento", "Valor", "Saldo", "Status", "Motivo", "Destino/origem", "Operador", "Terminal"], movementRows)}<h2>Recebimentos</h2>${table(["Data", "Pedido", "Forma", "Tipo", "Valor", "Troco"], saleRows)}<h2>Pedidos</h2>${table(["Pedido", "Referência", "Tipo", "Abertura", "Fechamento", "Operador", "Fechado por", "Status", "Pagamento", "Subtotal", "Serviço", "Desconto", "Entrega", "Total", "Observações/falhas"], orderRows)}<h2>Itens dos pedidos</h2>${table(["Pedido", "Referência", "Produto", "Qtd.", "Unitário", "Total", "Status", "Variações", "Adicionais", "Observações/falhas"], itemRows)}</body></html>`);
  popup.document.close();
  popup.focus();
  setTimeout(() => popup.print(), 150);
  return true;
}
