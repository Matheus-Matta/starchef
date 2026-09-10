/**
 * Endereço do editor visual do storefront (app Nuxt separado, ver `storefront/`).
 *
 * O painel (este app) faz o CRUD de metadados — site, páginas, SEO, tema,
 * imagens, domínios. Quem monta o conteúdo em blocos (GrapesJS) é o Nuxt; o
 * painel só abre um link para lá, na mesma lógica de `API_BASE_URL` em
 * `services/api.js` (permite trocar o destino em runtime sem rebuild).
 */
export const STOREFRONT_EDITOR_URL = (
  window.RUNTIME_CONFIG?.STOREFRONT_EDITOR_URL ||
  import.meta.env.VITE_STOREFRONT_EDITOR_URL ||
  "http://localhost:3100"
).replace(/\/+$/, "");

export function storefrontEditorUrl(pageId) {
  return `${STOREFRONT_EDITOR_URL}/editor/${pageId}`;
}
