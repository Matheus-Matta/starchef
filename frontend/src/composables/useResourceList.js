import { ref } from "vue";

import { normalizeApiError } from "../utils/apiError";

/**
 * Presenter (MVP) da listagem de um recurso.
 *
 * Concentra estado + regras de busca, ordenação e paginação server-side para a
 * View só cuidar do template. A View injeta filtros específicos via `buildParams`
 * (ex.: filtros do cardápio), mantendo o composable 100% genérico.
 *
 * Paginação, ordenação e busca são enviadas ao backend como parâmetros
 * padronizados (`page`, `page_size`, `ordering`, `search`) — a tabela nunca
 * carrega todos os registros de uma vez (STC-010/STC-012/STC-013).
 *
 * @param {object} options
 * @param {import("../services/ResourceService").ResourceService} options.service
 * @param {object} [options.defaultParams]  Parâmetros fixos aplicados a toda busca.
 * @param {() => object} [options.buildParams]  Parâmetros dinâmicos (filtros da tela).
 * @param {number} [options.pageSize]  Tamanho de página inicial.
 */
export function useResourceList({ service, defaultParams = {}, buildParams, pageSize = 25 } = {}) {
  const rows = ref([]);
  const total = ref(0);
  const page = ref(1);
  const rowsPerPage = ref(pageSize);
  const ordering = ref(""); // formato DRF: "campo" (asc) ou "-campo" (desc)
  const nextUrl = ref("");
  const previousUrl = ref("");
  const loading = ref(false);
  const error = ref("");

  const search = ref("");

  /** Normaliza a resposta do DRF (paginada ou lista pura) para o estado local. */
  function applyResponse(data) {
    rows.value = data.results || data || [];
    total.value = data.count ?? rows.value.length;
    nextUrl.value = data.next || "";
    previousUrl.value = data.previous || "";
  }

  /** Executa uma requisição protegida por loading/erro (mensagem normalizada). */
  async function run(request) {
    loading.value = true;
    error.value = "";
    try {
      applyResponse(await request());
    } catch (err) {
      error.value = normalizeApiError(err).message;
      rows.value = [];
      total.value = 0;
    } finally {
      loading.value = false;
    }
  }

  /** Monta os parâmetros da requisição a partir do estado atual. */
  function currentParams() {
    const params = {
      ...defaultParams,
      ...(buildParams ? buildParams() : {}),
      page: page.value,
      page_size: rowsPerPage.value,
    };
    if (search.value) params.search = search.value;
    if (ordering.value) params.ordering = ordering.value;
    return params;
  }

  /** Recarrega a página atual aplicando busca + filtros + ordenação. */
  function load() {
    return run(() => service.list(currentParams()));
  }

  /** Volta para a primeira página e recarrega (uso ao buscar/filtrar/ordenar). */
  function reload() {
    page.value = 1;
    return load();
  }

  /** Vai para uma página específica (1-indexed). */
  function goToPage(nextPage) {
    page.value = Math.max(1, nextPage);
    return load();
  }

  /** Altera o tamanho de página e volta à primeira. */
  function setPageSize(size) {
    rowsPerPage.value = size;
    return reload();
  }

  /**
   * Define a ordenação a partir do evento de sort do DataTable.
   * @param {string} field  Campo da coluna.
   * @param {number} order  1 (asc) | -1 (desc) | 0/null (limpar).
   */
  function setSort(field, order) {
    if (!field || !order) ordering.value = "";
    else ordering.value = order < 0 ? `-${field}` : field;
    return reload();
  }

  /** Navega para uma URL `next`/`previous` do DRF (compat.). */
  function loadUrl(url) {
    if (!url) return Promise.resolve();
    return run(() => service.listByUrl(url));
  }

  return {
    rows, total, page, rowsPerPage, ordering, nextUrl, previousUrl, loading, error, search,
    load, reload, goToPage, setPageSize, setSort, loadUrl,
  };
}
