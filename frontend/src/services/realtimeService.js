import { computed, readonly, ref } from "vue";

import { API_BASE_URL } from "./api";

const state = ref("idle");
const lastEvent = ref(null);
const listeners = new Map();
let socket = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let attempts = 0;
let manuallyStopped = false;

export function websocketUrl() {
  const configured = window.RUNTIME_CONFIG?.WS_URL || import.meta.env.VITE_WS_BASE_URL;
  // Sem WS_URL explícito o socket segue a ORIGEM DA API, não a do SPA: quando a
  // API mora em outro host (ex.: api.dominio enquanto o SPA está em dominio), o
  // /ws/ só existe atrás do proxy da API — apontar para a origem da página cai
  // no servidor de estáticos e o handshake falha.
  const url = new URL(configured || API_BASE_URL, window.location.href);
  // http(s) -> ws(s): `new WebSocket("https://...")` lança SyntaxError. Um
  // WS_URL que já venha como ws:/wss: é preservado como está.
  if (url.protocol === "https:") url.protocol = "wss:";
  else if (url.protocol === "http:") url.protocol = "ws:";
  url.pathname = "/ws/realtime/";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function emit(message) {
  lastEvent.value = { ...message, receivedAt: Date.now() };
  const callbacks = [
    ...(listeners.get(message.event) || []),
    ...(listeners.get("*") || []),
  ];
  callbacks.forEach((callback) => callback(message.payload || {}, message));
}

function scheduleReconnect() {
  if (manuallyStopped || reconnectTimer) return;
  const delay = Math.min(30_000, 1_000 * (2 ** attempts++));
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function connect() {
  manuallyStopped = false;
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
  state.value = "connecting";
  socket = new WebSocket(websocketUrl());
  socket.onopen = () => {
    state.value = "connected";
    attempts = 0;
    heartbeatTimer = window.setInterval(() => send("ping"), 25_000);
  };
  socket.onmessage = ({ data }) => {
    try { emit(JSON.parse(data)); } catch { /* ignore malformed server frames */ }
  };
  socket.onerror = () => socket?.close();
  socket.onclose = () => {
    socket = null;
    state.value = "disconnected";
    if (heartbeatTimer) window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    scheduleReconnect();
  };
}

function disconnect() {
  manuallyStopped = true;
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  if (heartbeatTimer) window.clearInterval(heartbeatTimer);
  reconnectTimer = null;
  heartbeatTimer = null;
  socket?.close();
  socket = null;
  state.value = "idle";
}

function send(event, payload = {}) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ event, payload }));
  }
}

function subscribe(event, callback) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(callback);
  return () => {
    listeners.get(event)?.delete(callback);
    if (!listeners.get(event)?.size) listeners.delete(event);
    if (!listeners.size) disconnect();
  };
}

export const realtimeService = {
  state: readonly(state),
  connected: computed(() => state.value === "connected"),
  lastEvent: readonly(lastEvent),
  connect,
  disconnect,
  send,
  subscribe,
};
