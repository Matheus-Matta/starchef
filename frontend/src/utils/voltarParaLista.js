/**
 * O "Voltar" das telas de registro: volta para a lista COMO ESTAVA.
 *
 * Antes, o botão fazia `router.push({ name })` — a lista abria pelo endereço
 * limpo e os filtros, a página e a rolagem sumiam. Duas regras:
 *
 * 1. A entrada anterior do histórico É a lista: volta pelo histórico, igual ao
 *    botão Voltar do navegador (filtros na URL, cache e rolagem intactos).
 * 2. Chegou ao registro por outro caminho (link, F5, depois de salvar um novo):
 *    abre a lista com os últimos filtros usados nela, que o `useListUrlState`
 *    guarda aqui a cada mudança.
 */
const lembradas = new Map();

export function lembrarLista(nomeDaRota, query) {
  if (nomeDaRota) lembradas.set(String(nomeDaRota), { ...query });
}

export function esquecerListas() {
  lembradas.clear();
}

export function voltarParaLista(router, nomeDaRota) {
  const lista = router.resolve({ name: nomeDaRota }).path;
  // O vue-router guarda em `history.state.back` o endereço da entrada anterior.
  const anterior = window.history.state?.back;
  if (anterior && String(anterior).split("?")[0] === lista) return router.back();
  return router.push({ name: nomeDaRota, query: lembradas.get(String(nomeDaRota)) || {} });
}
