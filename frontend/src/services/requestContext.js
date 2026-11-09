/**
 * De onde a requisição parte: o restaurante ativo e o terminal.
 * Aplicados a toda chamada do `api` (ver `api.js`).
 */
import { getBrowserValue } from "./browserPersistence";
import { terminalInstallationId, terminalNameHeader } from "./terminalIdentity";

export function isAuthRequest(url = "") {
  return url.includes("/auth/");
}

/**
 * Diz DE ONDE a requisição partiu, em toda chamada.
 *
 * A sessão de caixa pertence ao par (operador, terminal), e a checagem vale
 * para recuperar, pagar, sangrar, suprir e fechar — não só para abrir. Mandar
 * a identidade em um cabeçalho, e não apenas no corpo de `/open/`, é o que
 * evita ter de lembrar de incluí-la em cada endpoint novo.
 */
export function applyTerminalIdentity(config) {
  if (isAuthRequest(config.url)) return;
  config.headers = config.headers || {};
  if (!config.headers["X-Terminal-Id"]) {
    config.headers["X-Terminal-Id"] = terminalInstallationId();
    config.headers["X-Terminal-Name"] = terminalNameHeader();
  }
}

/** O restaurante ativo vai no cabeçalho e, nas leituras, também como filtro. */
export function applyRestaurantScope(config) {
  if (config.skipRestaurantScope || isAuthRequest(config.url)) return;
  const restaurantId = getBrowserValue("starchef-restaurant-scope");
  if (!restaurantId) return;

  config.headers = config.headers || {};
  if (!config.headers["X-Restaurant-ID"]) config.headers["X-Restaurant-ID"] = restaurantId;

  if (String(config.method || "get").toLowerCase() === "get") {
    config.params = { ...(config.params || {}) };
    if (!Object.prototype.hasOwnProperty.call(config.params, "restaurant")) config.params.restaurant = restaurantId;
  }
}
