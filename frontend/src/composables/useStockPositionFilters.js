import { ref } from "vue";

import { api } from "../services/api";

/**
 * Filtros por fornecedor e categoria e o CSV da posição de estoque.
 *
 * O filtro é feito no servidor, que sabe quais produtos consomem cada insumo
 * (o insumo não tem categoria própria).
 */
export function useStockPositionFilters(baseParams = () => ({})) {
  const supplierId = ref(null);
  const categoryId = ref(null);
  const suppliers = ref([]);
  const categories = ref([]);

  function params() {
    return Object.fromEntries(
      Object.entries({ ...baseParams(), supplier: supplierId.value, category: categoryId.value })
        .filter(([, value]) => value),
    );
  }

  async function loadFilterOptions() {
    try {
      const [fornecedores, categorias] = await Promise.all([
        api.get("/stock/suppliers/", { params: { is_active: true, page_size: 300 } }),
        api.get("/menu/categories/", { params: { page_size: 300 } }),
      ]);
      suppliers.value = fornecedores.data.results || fornecedores.data;
      categories.value = categorias.data.results || categorias.data;
    } catch {
      // Sem as opções a tela continua funcionando, só sem esses dois filtros.
    }
  }

  async function exportCsv() {
    const query = new URLSearchParams({ ...params(), export: "csv" });
    const resposta = await api.get(`/stock/positions/?${query}`, { responseType: "blob" });
    const url = URL.createObjectURL(resposta.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "posicao_de_estoque.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return { supplierId, categoryId, suppliers, categories, params, loadFilterOptions, exportCsv };
}
