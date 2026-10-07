import { useRealtimeResource } from "./useRealtimeResource";
import { applyRealtimeChange, listIsAtRest, matchesFixedParams } from "../utils/realtimeRows";

/**
 * Liga uma lista paginada ao tempo real mexendo na LINHA, não na página.
 *
 * Busca só o registro do evento (`service.retrieve`) e aplica com
 * `applyRealtimeChange`. Com filtro, busca, ordenação escolhida ou fora da
 * página 1, não faz nada — ver `utils/realtimeRows.js`.
 */
// Rajada: uma importação de 500 linhas são 500 eventos. Buscar linha a linha
// viraria 500 GETs por aba aberta — pior que reler a página. Acima de
// BURST_LIMIT eventos na janela, a lista espera a rajada acabar e relê UMA vez.
export const BURST_LIMIT = 20;
const BURST_WINDOW_MS = 1500;
const BURST_QUIET_MS = 800;

export function useRealtimeRows({
  resource, service, rows, total, page, rowsPerPage, ordering, filterCount,
  fixedParams = {}, recencyOrdered = true, onBurst = null, now = () => Date.now(),
}) {
  const recentes = [];
  let emRajada = false;
  let timerRajada = null;

  function registrarEvento() {
    const agora = now();
    recentes.push(agora);
    while (recentes.length && agora - recentes[0] > BURST_WINDOW_MS) recentes.shift();
    if (onBurst && recentes.length > BURST_LIMIT) emRajada = true;
    if (!emRajada) return false;
    clearTimeout(timerRajada);
    timerRajada = setTimeout(() => {
      emRajada = false;
      recentes.length = 0;
      if (atRest()) onBurst();
    }, BURST_QUIET_MS);
    return true;
  }

  const atRest = () => listIsAtRest({ page: page.value, filterCount: filterCount.value, ordering: ordering.value });

  async function apply(payload) {
    if (!atRest()) return;
    if (registrarEvento()) return; // rajada: relê uma vez no fim
    if (!payload.id) return; // evento de lote (sem id): sem linha
    let record = null;
    if (payload.action !== "deleted") {
      try {
        record = await service.retrieve(payload.id);
      } catch {
        record = null; // 404 = fora do escopo deste usuário/restaurante
      }
      if (record && !matchesFixedParams(record, fixedParams)) record = null;
    }
    if (!atRest()) return; // filtrou ou mudou de página enquanto buscava
    const next = applyRealtimeChange({
      rows: rows.value, total: total.value, pageSize: rowsPerPage.value,
      action: payload.action, record, id: payload.id, recencyOrdered,
    });
    rows.value = next.rows;
    total.value = next.total;
  }

  // Sem debounce: cada evento é uma linha, e nenhum pode se perder.
  useRealtimeResource(resource, apply, { debounce: 0 });
  return { apply };
}
