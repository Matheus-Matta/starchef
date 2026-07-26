import axios from "axios";

import { clearSession, hasSession } from "./tokenStorage";

// Base RELATIVA por padrão: o app chama a própria origem e o dev server (Vite)
// faz proxy para o backend. Mantém tudo na mesma origem — essencial para os
// cookies httpOnly de auth funcionarem (inclusive por trás de devtunnel).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

// `withCredentials: true` → o navegador envia/recebe os cookies httpOnly de auth.
const authClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
  timeout: 15_000,
});

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
  timeout: 15_000,
});

let refreshPromise = null;

api.interceptors.request.use((config) => {
  // O access token vai automaticamente pelo cookie httpOnly. Só mexemos no
  // Authorization quando o chamador o define explicitamente (sessão temporária).
  applyRestaurantScope(config);
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;

    if (status === 401 && original && !original._retry && !isAuthRefreshRequest(original.url)) {
      original._retry = true;
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return api(original);
      }
    }

    // Somente 401 (nao autenticado / token invalido) encerra a sessao.
    // 403 significa autenticado porem sem permissao (ex.: modulo desabilitado):
    // isso NAO deve deslogar o usuario — apenas propaga o erro para a tela tratar.
    if (status === 401) {
      clearSession();
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }

    return Promise.reject(error);
  },
);

function isAuthRefreshRequest(url = "") {
  return url.includes("/auth/refresh/");
}

function applyRestaurantScope(config) {
  if (config.skipRestaurantScope || String(config.method || "get").toLowerCase() !== "get") {
    return;
  }

  const restaurantId = localStorage.getItem("starchef-restaurant-scope");
  if (!restaurantId || isAuthRequest(config.url)) {
    return;
  }

  config.params = { ...(config.params || {}) };
  if (!config.params.restaurant) {
    config.params.restaurant = restaurantId;
  }
}

function isAuthRequest(url = "") {
  return url.includes("/auth/");
}

/** Renova o access token usando o refresh do cookie httpOnly (sem corpo). */
export async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = authClient
      .post("/auth/refresh/", {})
      .then((response) => response.data || true)
      .catch((error) => {
        clearSession();
        window.dispatchEvent(new CustomEvent("auth:unauthorized"));
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  try {
    return await refreshPromise;
  } catch {
    return null;
  }
}

/**
 * @param {object} credentials
 * @param {{ temporary?: boolean }} [options] `temporary` faz um login que NÃO
 *   grava cookies (usado na autorização gerencial do caixa, para não sobrescrever
 *   a sessão do operador).
 */
export async function loginRequest(credentials, { temporary = false } = {}) {
  return authClient.post("/auth/login/", { ...credentials, ...(temporary ? { no_cookie: true } : {}) });
}

export async function temporaryAuthenticatedPost(path, payload, access) {
  return authClient.post(path, payload, {
    headers: { Authorization: `Bearer ${access}` },
  });
}

export async function closeTemporarySession(access, refresh) {
  if (!access || !refresh) return;
  try {
    // `no_cookie: true` → apenas revoga o refresh temporário, sem limpar os
    // cookies httpOnly da sessão real do operador.
    await authClient.post(
      "/auth/logout/",
      { refresh, no_cookie: true },
      { headers: { Authorization: `Bearer ${access}` } },
    );
  } catch {
    // A credencial temporária nunca é persistida; falha no blacklist não
    // deve interferir na sessão principal do operador.
  }
}

export { hasSession };
