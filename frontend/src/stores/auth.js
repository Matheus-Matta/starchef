import { defineStore } from "pinia";

import { api, loginRequest, refreshAccessToken, verifyAccessToken } from "../services/api";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "../services/tokenStorage";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    accessToken: getAccessToken(),
    refreshToken: getRefreshToken(),
    user: null,
    initialized: false,
    loading: false,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken && state.refreshToken),
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
    setSession({ access, refresh, user }) {
      setTokens({ access, refresh });
      this.accessToken = access || getAccessToken();
      this.refreshToken = refresh || getRefreshToken();
      if (user !== undefined) this.user = user;
    },

    clearSession() {
      clearTokens();
      this.accessToken = null;
      this.refreshToken = null;
      this.user = null;
      this.initialized = true;
    },

    async login({ username, password }) {
      this.loading = true;
      try {
        const response = await loginRequest({ username, password });
        this.setSession({
          access: response.data.access,
          refresh: response.data.refresh,
          user: response.data.user,
        });
        this.initialized = true;
        return response.data.user;
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
      if (!this.accessToken && !this.refreshToken) {
        this.clearSession();
        return false;
      }

      try {
        if (this.accessToken) {
          await verifyAccessToken(this.accessToken);
        } else {
          const refreshed = await refreshAccessToken();
          this.accessToken = refreshed?.access || getAccessToken();
          this.refreshToken = refreshed?.refresh || getRefreshToken();
        }

        await this.fetchMe();
        this.initialized = true;
        return true;
      } catch {
        if (this.refreshToken) {
          try {
            const refreshed = await refreshAccessToken();
            this.accessToken = refreshed?.access || getAccessToken();
            this.refreshToken = refreshed?.refresh || getRefreshToken();
            await verifyAccessToken(this.accessToken);
            await this.fetchMe();
            this.initialized = true;
            return true;
          } catch {
            this.clearSession();
            return false;
          }
        }

        this.clearSession();
        return false;
      }
    },

    async logout() {
      const refresh = this.refreshToken;
      try {
        if (refresh) await api.post("/auth/logout/", { refresh });
      } finally {
        this.clearSession();
      }
    },
  },
});
