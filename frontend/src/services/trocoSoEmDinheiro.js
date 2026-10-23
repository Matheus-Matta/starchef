/**
 * Troco só em dinheiro, quando o restaurante desliga `allow_change_on_non_cash`.
 *
 * É a mesma regra do servidor (`backend/apps/payments/troco.py`), conferida
 * AQUI para o operador ver o aviso antes de mandar: cartão, PIX e voucher não
 * passam do restante. Devolve o aviso, ou "" quando pode.
 */
export function recusaDoTroco({ restaurante, forma, recebido, restante }) {
  if (!forma || forma.method_type === "cash") return "";
  if (restaurante?.allow_change_on_non_cash !== false) return "";
  if (Number(recebido) <= Number(restante) + 0.009) return "";
  const maximo = Number(restante).toFixed(2).replace(".", ",");
  return `Este restaurante dá troco só em dinheiro: em ${forma.name}, receba no máximo R$ ${maximo}.`;
}
