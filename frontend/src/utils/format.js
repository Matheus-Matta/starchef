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

/**
 * Arredonda para cima até o centavo — **para EXIBIR, nunca para gravar**.
 *
 * Ex.: 4.16 -> 4.16 | 4.1601 -> 4.17 | 4.1667 -> 4.17 | 10.00 -> 10.00
 *
 * A regra do projeto é que dinheiro nunca é `float` (ver
 * `docs/PADROES_DE_CODIGO.md`), e o JavaScript só tem `Number`. Por isso esta
 * função é de APRESENTAÇÃO: ela serve para mostrar um custo unitário derivado
 * de uma divisão (total ÷ quantidade dá 4,1667 e o operador precisa ler 4,17).
 *
 * **O valor que sai daqui não pode ser enviado ao servidor nem persistido.**
 * Quem decide preço é o backend, em `Decimal` — mandar de volta um número que
 * passou por float é como o total do PDV e o do servidor divergem por um
 * centavo, que é um defeito que este projeto já pagou uma vez.
 *
 * Valor negativo ou inválido devolve `0` de propósito: a função existe para um
 * custo unitário, que não é negativo. Se algum dia ela precisar de desconto ou
 * crédito, o contrato muda e este comentário tem de mudar junto — não passe um
 * negativo esperando `-4,17`.
 */
export function roundUpToCent(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return 0;
  // O `Math.round` em 1e6 absorve o ruído do float ANTES do arredondamento de
  // centavo: sem ele, `4.16 * 100` vira 415.99999999999994 e `Math.ceil`
  // devolveria 4,16 num caso e 4,17 no outro, sem regra visível.
  const scaled = Math.round(num * 1e6) / 1e4;
  return Math.ceil(scaled) / 100;
}
