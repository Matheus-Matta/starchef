import { onMounted, onUnmounted } from "vue";

import { realtimeService } from "../services/realtimeService";

export function useRealtimeResource(resources, callback, { debounce = 120 } = {}) {
  const accepted = new Set(Array.isArray(resources) ? resources : [resources]);
  let unsubscribe = null;
  let timer = null;

  function handle(payload, message) {
    if (!accepted.has("*") && !accepted.has(payload.resource) && !accepted.has(payload.model)) return;
    // Sem debounce, CADA evento chega: quem mexe linha a linha não pode
    // perder o primeiro de dois pedidos que entraram no mesmo instante.
    if (debounce <= 0) {
      callback(payload, message);
      return;
    }
    window.clearTimeout(timer);
    timer = window.setTimeout(() => callback(payload, message), debounce);
  }

  onMounted(() => {
    realtimeService.connect();
    unsubscribe = realtimeService.subscribe("*", handle);
  });
  onUnmounted(() => {
    unsubscribe?.();
    window.clearTimeout(timer);
  });

  return {
    connectionState: realtimeService.state,
    connected: realtimeService.connected,
    lastEvent: realtimeService.lastEvent,
  };
}

