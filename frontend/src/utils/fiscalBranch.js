import { ResourceService } from "../services/ResourceService";

const branchService = new ResourceService({ endpoint: "/branches/", globalScope: true });

/**
 * Acha a filial de um restaurante — a configuração fiscal (FiscalConfig/
 * FiscalProfile) é vinculada à filial, não ao restaurante diretamente.
 *
 * Branch não tem filtro por restaurante na API (evita um problema já
 * conhecido de escopo assíncrono), então busca a lista inteira (poucas
 * filiais por conta) e filtra no cliente. Reaproveitado onde quer que se
 * precise "a filial deste restaurante" — hoje a seção fiscal do restaurante
 * e o formulário de produto (criação rápida de perfil fiscal).
 */
export async function resolveBranchIdForRestaurant(restaurantId) {
  const { results } = await branchService.list({ page_size: 200 });
  const branch = (results || []).find((b) => b.restaurant === restaurantId);
  return branch?.id || null;
}
