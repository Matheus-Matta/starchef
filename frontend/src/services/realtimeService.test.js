import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * O WS precisa seguir a origem da API: em produção o SPA e a API podem estar em
 * hosts diferentes (starchef.com.br x api.starchef.com.br) e o /ws/ só existe
 * atrás do proxy da API.
 */
async function loadWebsocketUrl(runtimeConfig) {
  vi.resetModules();
  window.RUNTIME_CONFIG = runtimeConfig;
  const { websocketUrl } = await import("./realtimeService");
  return websocketUrl();
}

describe("websocketUrl", () => {
  afterEach(() => {
    delete window.RUNTIME_CONFIG;
    vi.resetModules();
  });

  it("deriva do host da API quando ela está em outra origem", async () => {
    const url = await loadWebsocketUrl({ API_URL: "https://api.exemplo.com.br/api/v1" });
    expect(url).toBe("wss://api.exemplo.com.br/ws/realtime/");
  });

  it("usa a origem da página quando a API é relativa (same-origin)", async () => {
    const url = await loadWebsocketUrl({ API_URL: "/api/v1" });
    expect(url).toBe(`ws://${window.location.host}/ws/realtime/`);
  });

  it("respeita WS_URL explícito", async () => {
    const url = await loadWebsocketUrl({
      API_URL: "https://api.exemplo.com.br/api/v1",
      WS_URL: "wss://ws.exemplo.com.br",
    });
    expect(url).toBe("wss://ws.exemplo.com.br/ws/realtime/");
  });

  it("ignora WS_URL vazio (entrypoint injeta string vazia quando não configurado)", async () => {
    const url = await loadWebsocketUrl({ API_URL: "https://api.exemplo.com.br/api/v1", WS_URL: "" });
    expect(url).toBe("wss://api.exemplo.com.br/ws/realtime/");
  });
});
