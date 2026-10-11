import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAutoRefresh } from "./useAutoRefresh";

function montar(carregar) {
  return mount(defineComponent({
    setup() {
      useAutoRefresh(carregar, 30_000);
      return () => h("div");
    },
  }));
}

describe("useAutoRefresh", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("recarrega a cada 30 segundos, em silencio", async () => {
    const carregar = vi.fn().mockResolvedValue();
    montar(carregar);

    await vi.advanceTimersByTimeAsync(30_000);
    await vi.advanceTimersByTimeAsync(30_000);

    expect(carregar).toHaveBeenCalledTimes(2);
    expect(carregar).toHaveBeenCalledWith({ silencioso: true });
  });

  it("nao empilha: com a anterior ainda carregando, pula a vez", async () => {
    let terminar;
    const carregar = vi.fn(() => new Promise((ok) => { terminar = ok; }));
    montar(carregar);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(carregar).toHaveBeenCalledTimes(1);

    terminar();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(carregar).toHaveBeenCalledTimes(2);
  });

  it("para ao sair da tela", async () => {
    const carregar = vi.fn().mockResolvedValue();
    montar(carregar).unmount();

    await vi.advanceTimersByTimeAsync(90_000);

    expect(carregar).not.toHaveBeenCalled();
  });

  it("aba escondida nao consulta o servidor", async () => {
    const carregar = vi.fn().mockResolvedValue();
    const oculto = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    montar(carregar);

    await vi.advanceTimersByTimeAsync(60_000);

    expect(carregar).not.toHaveBeenCalled();
    oculto.mockRestore();
  });
});
