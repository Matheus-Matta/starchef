/**
 * Divergência de vendas: o dinheiro que entrou no caixa sem venda registrada
 * no PDV (num pico, pedidos passam sem lançamento).
 *
 * NÃO é pedido nem NFC-e — é o registro administrativo da diferença. A
 * regularização fiscal (ex.: denúncia espontânea) é decidida pelo contador, e
 * o sistema só guarda o desfecho.
 */
import { api } from "./api";

export const DISCREPANCY_STATUS = {
  open: { label: "Aberta", tone: "warning" },
  reviewed: { label: "Analisada", tone: "info" },
  regularized: { label: "Regularizada", tone: "success" },
  cancelled: { label: "Cancelada", tone: "secondary" },
};

export const statusLabel = (status) => DISCREPANCY_STATUS[status]?.label || status;
export const statusTone = (status) => DISCREPANCY_STATUS[status]?.tone || "secondary";

/** O que cada decisão pede ao operador. */
export const DECISIONS = {
  review: { title: "Marcar como analisada", field: null, button: "Marcar como analisada" },
  regularize: {
    title: "Registrar regularização",
    field: "note",
    label: "Como foi regularizado",
    placeholder: "Ex.: denúncia espontânea, protocolo 2026/123, orientada pelo contador.",
    button: "Registrar regularização",
  },
  cancel: {
    title: "Cancelar divergência",
    field: "reason",
    label: "Motivo do cancelamento",
    placeholder: "Ex.: registrada em dobro.",
    button: "Cancelar divergência",
  },
};

/** Ações possíveis em cada estado (o backend revalida e responde 409). */
export function availableDecisions(status) {
  if (status === "open") return ["review", "regularize", "cancel"];
  if (status === "reviewed") return ["regularize", "cancel"];
  return [];
}

/** Soma em centavos: dinheiro nunca é somado em ponto flutuante. */
export function totalInCents(amounts) {
  return Object.values(amounts || {}).reduce((sum, value) => sum + Math.round(Number(value || 0) * 100), 0);
}

export const centsToMoney = (cents) => (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** `{metodoId: valor}` -> corpo da API, só com o que foi preenchido. */
export function buildPayload({ cashRegister, amounts, reason, notes }) {
  return {
    cash_register: cashRegister,
    reason: (reason || "").trim(),
    notes: (notes || "").trim(),
    by_payment_method: Object.entries(amounts || {})
      .filter(([, value]) => Math.round(Number(value || 0) * 100) > 0)
      .map(([id, value]) => ({ payment_method: id, amount: (Math.round(Number(value) * 100) / 100).toFixed(2) })),
  };
}

export const registerDiscrepancy = (payload) => api.post("/cash-discrepancies/", payload);
export const listDiscrepancies = (cashRegister) =>
  api.get("/cash-discrepancies/", { params: { cash_register: cashRegister, page_size: 100 } });
export const decide = (id, decision, body = {}) => api.post(`/cash-discrepancies/${id}/${decision}/`, body);
export const fetchReport = (ids) =>
  api.get("/cash-discrepancy-report/", { params: { cash_registers: ids.join(",") } });
