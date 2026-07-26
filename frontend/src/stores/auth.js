import { defineStore } from "pinia";

import { api, loginRequest, refreshAccessToken } from "../services/api";
import { clearSession, hasSession } from "../services/tokenStorage";

const SESSION_VALIDATION_TTL_MS = 30_000;
let lastValidatedAt = 0;

export const useAuthStore = defineStore("auth", {
  state: () => ({
    // Os tokens vivem em cookies httpOnly; aqui só sabemos SE há sessão ativa.
    authed: hasSession(),
    user: null,
    initialized: false,
    loading: false,
  }),

  getters: {
    isAuthenticated: (state) => state.authed,
    // Modulos habilitados para a conta em sessao (o base e sempre implicito).
    enabledModules: (state) => state.user?.enabled_modules || ["base"],
    /** Testa se um modulo esta liberado. Reativo: usado por sidebar e router guard. */
    hasModule: (state) => (moduleName) => {
      if (!moduleName || moduleName === "base") return true;
      // Superadmin (dono da plataforma) sobrepoe o licenciamento: enxerga todos os modulos.
      if (state.user?.is_superuser) return true;
      return (state.user?.enabled_modules || []).includes(moduleName);
    },
  },

  actions: {
    clearLocal() {
      clearSession();
      lastValidatedAt = 0;
      this.authed = false;
      this.user = null;
      this.initialized = true;
    },

    async login({ username, password }) {
      this.loading = true;
      try {
        const response = await loginRequest({ username, password });
        this.authed = true;
        this.user = response.data?.user || null;
        if (!this.user) await this.fetchMe();
        lastValidatedAt = Date.now();
        this.initialized = true;
        return this.user;
      } finally {
        this.loading = false;
      }
    },

    async fetchMe() {
      const response = await api.get("/auth/me/");
      this.user = response.data;
      return response.data;
    },

    async validateSession() {
      if (!hasSession()) {
        this.clearLocal();
        return false;
      }
      if (this.authed && this.user && Date.now() - lastValidatedAt < SESSION_VALIDATION_TTL_MS) {
        return true;
      }
      try {
        // Cookie enviado automaticamente. Um 401 aqui dispara refresh + retry no
        // interceptor; se o refresh também falhar, a promessa rejeita.
        await this.fetchMe();
        this.authed = true;
        this.initialized = true;
        lastValidatedAt = Date.now();
        return true;
      } catch {
        // Última tentativa: refresh explícito e refetch (cobre corridas de token).
        try {
          const refreshed = await refreshAccessToken();
          if (!refreshed) throw new Error("refresh failed");
          await this.fetchMe();
          this.authed = true;
          this.initialized = true;
          lastValidatedAt = Date.now();
          return true;
        } catch {
          this.clearLocal();
          return false;
        }
      }
    },

    // Mantido por compatibilidade com chamadas externas (ex.: interceptor).
    clearSession() {
      this.clearLocal();
    },

    async logout() {
      try {
        await api.post("/auth/logout/", {});
      } finally {
        this.clearLocal();
      }
    },
  },
});
