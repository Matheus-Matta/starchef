import axios from "axios";

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./tokenStorage";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

const authClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

let refreshPromise = null;

api.interceptors.request.use((config) => {
  const accessToken = getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
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
      if (refreshed?.access) {
        original.headers.Authorization = `Bearer ${refreshed.access}`;
        return api(original);
      }
    }

    if (status === 401 || status === 403) {
      clearTokens();
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }

    return Promise.reject(error);
  },
);

function isAuthRefreshRequest(url = "") {
  return url.includes("/auth/refresh/");
}

export async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  if (!refreshPromise) {
    refreshPromise = authClient
      .post("/auth/refresh/", { refresh })
      .then((response) => {
        const tokens = {
          access: response.data.access,
          refresh: response.data.refresh || refresh,
        };
        setTokens(tokens);
        return tokens;
      })
      .catch((error) => {
        clearTokens();
        window.dispatchEvent(new CustomEvent("auth:unauthorized"));
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

export async function verifyAccessToken(access) {
  return authClient.post("/auth/verify/", { token: access });
}

export async function loginRequest(credentials) {
  return authClient.post("/auth/login/", credentials);
}
