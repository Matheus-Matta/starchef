/**
 * Formatadores de exibicao compartilhados por toda a aplicacao.
 * Fonte unica de verdade: evita a duplicacao que existia entre as views.
 */

const LOCALE = "pt-BR";

/** Formata um numero como moeda brasileira. Ex.: 12.5 -> "R$ 12,50". */
export function formatMoney(value) {
  return Number(value || 0).toLocaleString(LOCALE, { style: "currency", currency: "BRL" });
}

/**
 * Data + hora curtas. Retorna "-" quando vazio.
 * @param {string|Date} value
 * @param {{ withYear?: boolean }} [options] inclui o ano (usado nas telas de detalhe).
 */
export function formatDateTime(value, { withYear = false } = {}) {
  if (!value) return "-";
  return new Date(value).toLocaleString(LOCALE, {
    day: "2-digit",
    month: "2-digit",
    ...(withYear ? { year: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Numero com ate 3 casas decimais (pesos, quantidades). */
export function formatQuantity(value) {
  return Number(value || 0).toLocaleString(LOCALE, { maximumFractionDigits: 3 });
}

/** Percentual com ate 1 casa. Ex.: 12.5 -> "12,5%". */
export function formatPercent(value) {
  return `${Number(value || 0).toLocaleString(LOCALE, { maximumFractionDigits: 1 })}%`;
}

/** Traduz um valor bruto usando um mapa { valor: rotulo }; "-" quando vazio. */
export function mapLabel(value, map) {
  if (value == null || value === "") return "-";
  const mapped = map?.[value] ?? value;
  if (typeof mapped === "object" && mapped !== null && "label" in mapped) {
    return mapped.label;
  }
  return mapped;
}
