/**
 * Os campos da lista genérica que vão para a URL (ver `useListUrlState`).
 *
 *   /notas-fiscais?pagina=3&por_pagina=50&ordem=-created_at&busca=joão
 *                 &de=2026-11-01&ate=2026-11-09&f_status=error&situacao=ready
 *
 * Valor igual ao padrão da tela não vai para a URL: o endereço da lista "do
 * jeito que abre" continua limpo. O período é a exceção que precisa de um
 * terceiro estado — a tela que abre com "últimos 30 dias" e foi limpa vira
 * `periodo=todos`, senão voltar traria os 30 dias de novo.
 */
export function ymd(date) {
  if (!(date instanceof Date)) return "";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

const dataDe = (texto) => (texto ? new Date(`${texto}T00:00:00`) : null);
const intervaloEmTexto = (intervalo) => (Array.isArray(intervalo) ? intervalo.map(ymd).join("|") : "");

export function listUrlFields({ page, rowsPerPage, ordering, search, dateRange, filtros, situacao, padrao }) {
  const periodoPadrao = intervaloEmTexto(padrao.dateRange);
  const campos = [
    { chave: "pagina", ler: () => (page.value > 1 ? String(page.value) : ""),
      escrever: (v) => { page.value = Math.max(1, Number(v) || 1); } },
    { chave: "por_pagina", ler: () => (rowsPerPage.value !== padrao.pageSize ? String(rowsPerPage.value) : ""),
      escrever: (v) => { rowsPerPage.value = Number(v) || padrao.pageSize; } },
    // Ordem desligada numa tela que abre ordenada precisa dizer isso na URL.
    { chave: "ordem", ler: () => (ordering.value !== padrao.ordering ? ordering.value || "nenhuma" : ""),
      escrever: (v) => { ordering.value = v === "nenhuma" ? "" : v; } },
    { chave: "busca", ler: () => search.value?.trim() || "", escrever: (v) => { search.value = v; } },
    { chave: "periodo", ler: () => (!dateRange.value?.length && periodoPadrao ? "todos" : ""),
      escrever: (v) => { if (v === "todos") dateRange.value = null; } },
    { chave: "de", ler: () => (intervaloEmTexto(dateRange.value) !== periodoPadrao ? ymd(dateRange.value?.[0]) : ""),
      // `de` vem antes de `ate` na restauração: começa um intervalo novo, sem herdar o fim do padrão.
      escrever: (v) => { dateRange.value = [dataDe(v), null]; } },
    { chave: "ate", ler: () => (intervaloEmTexto(dateRange.value) !== periodoPadrao ? ymd(dateRange.value?.[1]) : ""),
      escrever: (v) => { dateRange.value = [dateRange.value?.[0] || null, dataDe(v)]; } },
    { prefixo: "f_", ler: () => filtros, escrever: (valores) => Object.assign(filtros, valores) },
  ];
  if (situacao) {
    campos.push({ chave: "situacao", ler: () => (situacao.value !== "all" ? situacao.value : ""),
                  escrever: (v) => { situacao.value = v; } });
  }
  return campos;
}
