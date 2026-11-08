/**
 * A situação fiscal da nota, no mesmo vocabulário de `fiscal_state_of` do
 * backend (apps/invoices/services.py). O resumo `fiscal` do pedido já a traz;
 * a nota inteira traz `status`, `emission_type` e `fiscal_payload.awaiting`,
 * e daqui sai a mesma resposta.
 */
export function fiscalStateOf(invoice) {
  if (!invoice) return "unknown";
  if (invoice.fiscal_state) return invoice.fiscal_state;
  if (invoice.status === "issued") return "authorized";
  if (invoice.status === "cancelled") return "cancelled";
  if (invoice.status === "error") {
    return invoice.fiscal_payload?.failure === "configuration" ? "configuration_error" : "rejected";
  }
  if (invoice.status === "pending") {
    const awaiting = invoice.fiscal_payload?.awaiting;
    if (awaiting === "reconciliation") return "reconciliation_required";
    if (awaiting === "authorization") return "processing";
    return invoice.emission_type === "9" ? "contingency_pending" : "awaiting_transmission";
  }
  return "draft";
}

export const RESENDABLE_STATES = ["rejected", "configuration_error", "contingency_pending", "awaiting_transmission"];

// Processando e em conciliação ficam de fora: a SEFAZ pode já ter a nota, e
// recriar daria duas notas para a mesma venda (o backend recusa com 409).
export const RECREATABLE_STATES = ["rejected", "configuration_error", "contingency_pending", "awaiting_transmission"];

// Para o resumo do pedido, que não traz o XML: estas situações sempre têm.
export const STATES_WITH_XML = ["authorized", "cancelled", "contingency_pending"];
