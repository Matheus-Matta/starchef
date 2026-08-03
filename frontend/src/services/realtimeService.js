import { computed, readonly, ref } from "vue";

const state = ref("idle");
const lastEvent = ref(null);
const listeners = new Map();
let socket = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let attempts = 0;
let manuallyStopped = false;

function websocketUrl() {
  const configured = window.RUNTIME_CONFIG?.WS_URL || import.meta.env.VITE_WS_BASE_URL;
  if (configured) return `${configured.replace(/\/$/, "")}/ws/realtime/`;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/realtime/`;
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
