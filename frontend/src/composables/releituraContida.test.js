import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { releituraContida } from "./releituraContida";

function esconder(valor) {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => valor });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("releituraContida", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    esconder(false);
  });
  afterEach(() => {
    vi.useRealTimers();
    esconder(false);
  });

  it("uma rajada de avisos vira uma leitura agora e UMA no fim do intervalo", () => {
    const carregar = vi.fn();
    const { pedir, parar } = releituraContida(carregar, { intervalo: 10000, agora: () => Date.now() });

    for (let i = 0; i < 40; i += 1) pedir();
    expect(carregar).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(10000);
    expect(carregar).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(60000);
    expect(carregar).toHaveBeenCalledTimes(2);
    parar();
  });

  it("aba escondida não lê; lê uma vez quando volta", () => {
    const carregar = vi.fn();
    const { pedir, parar } = releituraContida(carregar, { intervalo: 10000, agora: () => Date.now() });

    esconder(true);
    pedir();
    pedir();
    vi.advanceTimersByTime(60000);
    expect(carregar).not.toHaveBeenCalled();

    esconder(false);
    expect(carregar).toHaveBeenCalledTimes(1);
    parar();
  });

  it("parar cancela a leitura agendada", () => {
    const carregar = vi.fn();
    const { pedir, parar } = releituraContida(carregar, { intervalo: 10000, agora: () => Date.now() });
    pedir();
    pedir();
    parar();
    vi.advanceTimersByTime(20000);
    expect(carregar).toHaveBeenCalledTimes(1);
  });
});
