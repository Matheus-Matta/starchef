import { useAuthStore } from "../stores/auth";

const RESTAURANT_SCOPE_KEY = "starchef-restaurant-scope";

/**
 * Preenche `restaurant`/`branch` num payload de CRIACAO a partir do perfil do usuario
 * autenticado (com fallback ao escopo de restaurante escolhido pelo admin na sidebar).
 *
 * Todo model tenant-scoped exige `restaurant`; quando o model participa de uma
 * constraint de unicidade por filial (ex.: produto unico por branch+codigo), o DRF
 * tambem marca `branch` como obrigatorio — mesmo sendo opcional no model. Sem isso,
 * o back rejeita a criacao com "campo obrigatorio" antes do AuditCreateUpdateMixin
 * ter a chance de preencher esses campos a partir do perfil.
 *
 * So preenche campos que o proprio payload/form ainda nao definiu, para nao
 * sobrescrever uma escolha explicita do usuario (ex.: campo "restaurant" em
 * "kds-estacoes", que permite ao admin escolher outro restaurante).
 *
 * @param {object} payload  Objeto de payload a ser enviado no POST (mutado in-place).
 * @param {{ skip?: string[] }} [options]  Nomes de campos que ja sao geridos pelo form.
 */
export function applyTenantDefaults(payload, { skip = [] } = {}) {
  const skipSet = new Set(skip);
  const profile = useAuthStore().user;

  if (!skipSet.has("restaurant") && payload.restaurant == null) {
    const restaurantId = profile?.restaurant_id || localStorage.getItem(RESTAURANT_SCOPE_KEY);
    if (restaurantId) payload.restaurant = restaurantId;
  }
  if (!skipSet.has("branch") && payload.branch == null && profile?.branch_id) {
    payload.branch = profile.branch_id;
  }
  return payload;
}
