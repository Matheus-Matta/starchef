import { defineStore } from "pinia";

import { api, API_BASE_URL } from "../services/api";
import { hasSession } from "../services/tokenStorage";

const PAGE_SIZE = 10;

/** URL do WebSocket. A autenticação vai pelo cookie httpOnly no handshake. */
function buildWsUrl() {
  if (!hasSession()) return null;
  let httpBase = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  // Base relativa (ex.: "/api/v1" -> ""): usa a origem atual do app; o dev server
  // faz proxy do /ws para o backend, mantendo o handshake na mesma origem.
  if (!/^https?:\/\//i.test(httpBase)) {
    httpBase = window.location.origin;
  }
  const wsBase = httpBase.replace(/^http/, "ws");
  return `${wsBase}/ws/notifications/`;
}

export const useNotificationsStore = defineStore("notifications", {
  state: () => ({
    items: [],
    unreadCount: 0,
    nextPage: 1,
    hasMore: false,
    loading: false,
    started: false,
    socket: null,
    reconnectTimer: null,
    closedByUser: false,
  }),

  actions: {
    /** Inicializa: carrega a primeira página, a contagem e conecta o WS. */
    async init() {
      if (this.started) return;
      this.started = true;
      this.closedByUser = false;
      await Promise.all([this.fetchFirst(), this.fetchUnreadCount()]);
      this.connect();
    },

    async fetchFirst() {
      this.loading = true;
      try {
        const { data } = await api.get("/notifications/", { params: { page: 1, page_size: PAGE_SIZE }, skipRestaurantScope: true });
        this.items = data.results || data || [];
        this.hasMore = Boolean(data.next);
        this.nextPage = 2;
      } catch {
        this.items = [];
        this.hasMore = false;
      } finally {
        this.loading = false;
      }
    },

    async loadMore() {
      if (this.loading || !this.hasMore) return;
      this.loading = true;
      try {
        const { data } = await api.get("/notifications/", { params: { page: this.nextPage, page_size: PAGE_SIZE }, skipRestaurantScope: true });
        const rows = data.results || data || [];
        // Evita duplicatas caso novos itens tenham chegado por WS no topo.
        const seen = new Set(this.items.map((n) => n.id));
        this.items.push(...rows.filter((n) => !seen.has(n.id)));
        this.hasMore = Boolean(data.next);
        this.nextPage += 1;
      } finally {
        this.loading = false;
      }
    },

    async fetchUnreadCount() {
      try {
        const { data } = await api.get("/notifications/unread-count/", { skipRestaurantScope: true });
        this.unreadCount = data.unread || 0;
      } catch {
        /* silencioso */
      }
    },

    async markRead(id) {
      const item = this.items.find((n) => n.id === id);
      if (!item || item.is_read) return;
      item.is_read = true;
      this.unreadCount = Math.max(0, this.unreadCount - 1);
      try {
        await api.post(`/notifications/${id}/read/`, {}, { skipRestaurantScope: true });
      } catch {
        /* mantém otimista */
      }
    },

    async markAllRead() {
      if (!this.unreadCount) return;
      this.items.forEach((n) => { n.is_read = true; });
      this.unreadCount = 0;
      try {
        await api.post("/notifications/mark-all-read/", {}, { skipRestaurantScope: true });
      } catch {
        /* mantém otimista */
      }
    },

    /** Trata uma notificação recebida em tempo real via WS. */
    handleIncoming(payload) {
      if (!payload || !payload.id) return;
      if (this.items.some((n) => n.id === payload.id)) return;
      this.items.unshift(payload);
      if (!payload.is_read) this.unreadCount += 1;
    },

    connect() {
      const url = buildWsUrl();
      if (!url || (this.socket && this.socket.readyState <= 1)) return;
      try {
        const socket = new WebSocket(url);
        this.socket = socket;
        socket.onmessage = (event) => {
          let message;
          try { message = JSON.parse(event.data); } catch { return; }
          if (message.event === "notification") this.handleIncoming(message.payload);
          else if (message.event === "connected" && typeof message.payload?.unread === "number") this.unreadCount = message.payload.unread;
        };
        socket.onclose = () => {
          this.socket = null;
          if (!this.closedByUser) this.scheduleReconnect();
        };
        socket.onerror = () => { socket.close(); };
      } catch {
        this.scheduleReconnect();
      }
    },

    scheduleReconnect() {
      if (this.reconnectTimer || this.closedByUser) return;
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this.connect();
      }, 4000);
    },

    /** Encerra tudo (logout). */
    reset() {
      this.closedByUser = true;
      if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
      if (this.socket) { try { this.socket.close(); } catch { /* ignore */ } this.socket = null; }
      this.items = [];
      this.unreadCount = 0;
      this.nextPage = 1;
      this.hasMore = false;
      this.started = false;
    },
  },
});
