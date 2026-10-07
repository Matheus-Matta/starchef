/**
 * A mudança que chega pelo WebSocket aplicada NA LINHA, sem reler a página.
 *
 * Antes cada evento refazia o GET da página inteira — e o `reload` ainda
 * voltava para a página 1 quem estava conferindo a 3. Agora a tela busca só o
 * registro que mudou e mexe nele.
 *
 * Só a "tela inicial" da lista reage: página 1, sem filtro e na ordem padrão.
 * Com filtro, busca, outra página ou outra ordenação não dá para saber onde
 * (nem se) o registro entra, e a pessoa está olhando um recorte que ela mesma
 * escolheu — mexer nele por baixo atrapalha mais do que ajuda.
 */

/** A lista está no estado em que o tempo real pode mexer nela? */
export function listIsAtRest({ page, filterCount, ordering }) {
  return page === 1 && !filterCount && !ordering;
}

/**
 * O registro ainda pertence a esta tela pelos parâmetros fixos dela
 * (`defaultParams`, ex.: a lista de pedidos abertos manda `status=open`)?
 * Parâmetro que não é campo do registro não decide nada.
 */
export function matchesFixedParams(record, fixedParams = {}) {
  return Object.entries(fixedParams).every(([key, value]) => {
    if (value === "" || value == null || !(key in record)) return true;
    return String(record[key]) === String(value);
  });
}

/**
 * Nova lista e novo total depois da mudança.
 *
 * `record` nulo numa atualização significa "não pertence mais a esta tela"
 * (saiu do escopo, não bate os parâmetros fixos): a linha sai.
 */
export function applyRealtimeChange({
  rows, total, pageSize, action, record = null, id = record?.id, recencyOrdered = true,
}) {
  const key = String(id ?? "");
  const index = rows.findIndex((row) => String(row.id) === key);

  if (action === "deleted" || !record) {
    if (index < 0) return { rows, total };
    return { rows: rows.filter((_, i) => i !== index), total: Math.max(0, total - 1) };
  }
  if (index >= 0) {
    const next = rows.slice();
    next[index] = record;
    return { rows: next, total };
  }
  // Alterado e fora da página numa lista por nome/número: não há como saber
  // a posição dele sem reler — e no topo ficaria fora de ordem.
  if (action !== "created" && !recencyOrdered) return { rows, total };
  // Novo na tela: entra no topo (a ordem padrão é "mais recente primeiro") e,
  // com a página cheia, o último sai — a paginação continua com o mesmo tamanho.
  return { rows: [record, ...rows].slice(0, pageSize), total: total + 1 };
}
