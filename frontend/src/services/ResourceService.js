import { api } from "./api";
import { parseApiUrl } from "../utils/pagination";

/**
 * Camada Model do padrao MVP: encapsula todo o acesso HTTP de um recurso REST.
 *
 * Uma unica classe reutilizavel serve qualquer endpoint do backend, entao as
 * telas nunca montam URLs nem lidam com axios diretamente — elas conversam
 * apenas com uma instancia de ResourceService.
 *
 * @example
 *   const produtos = new ResourceService({ endpoint: "/menu/products/" });
 *   const page = await produtos.list({ search: "x" });
 *   const item = await produtos.retrieve(id);
 */
export class ResourceService {
  /**
   * @param {object} config
   * @param {string} config.endpoint  Caminho REST com barra final. Ex.: "/menu/products/".
   * @param {boolean} [config.globalScope=false]  Ignora o filtro automatico por restaurante.
   */
  constructor({ endpoint, globalScope = false }) {
    this.endpoint = endpoint;
    this.globalScope = globalScope;
  }

  /** Config extra do axios comum a todas as chamadas deste recurso. */
  get requestConfig() {
    return { skipRestaurantScope: this.globalScope };
  }

  /** Lista paginada. Retorna o payload cru do DRF ({ results, count, next, previous }). */
  async list(params = {}) {
    const { data } = await api.get(this.endpoint, { params, ...this.requestConfig });
    return data;
  }

  /** Carrega uma pagina a partir de uma URL absoluta `next`/`previous` do DRF. */
  async listByUrl(url) {
    const { path, params } = parseApiUrl(url);
    const { data } = await api.get(path, { params, ...this.requestConfig });
    return data;
  }

  /** Busca um unico registro pelo id. */
  async retrieve(id) {
    const { data } = await api.get(`${this.endpoint}${id}/`, this.requestConfig);
    return data;
  }

  /** Cria um novo registro. `extraConfig` mescla config extra do axios (ex.: headers). */
  async create(payload, extraConfig = {}) {
    const { data } = await api.post(this.endpoint, payload, extraConfig);
    return data;
  }

  /** Atualiza parcialmente um registro existente (PATCH). */
  async update(id, payload, extraConfig = {}) {
    const { data } = await api.patch(`${this.endpoint}${id}/`, payload, extraConfig);
    return data;
  }

  /** Remove um registro. */
  async remove(id) {
    await api.delete(`${this.endpoint}${id}/`);
  }

  /** GET de uma sub-acao de detalhe (ex.: `/commands/{id}/codes/`). */
  async detailAction(id, actionPath) {
    const { data } = await api.get(`${this.endpoint}${id}/${actionPath}/`, this.requestConfig);
    return data;
  }
}
