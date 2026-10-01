import { describe, expect, it } from "vitest";

import { isStaleChunkError, reloadOnce } from "./staleChunkReload";

function memoria() {
  const dados = new Map();
  return { getItem: (k) => dados.get(k) ?? null, setItem: (k, v) => dados.set(k, v) };
}

describe("aba numa versão antiga do painel", () => {
  it("reconhece o erro de arquivo de versão antiga, nos navegadores principais", () => {
    expect(isStaleChunkError(new TypeError(
      "Failed to fetch dynamically imported module: https://app.starchef.com.br/assets/HomeView-CRrZKTUq.js",
    ))).toBe(true);
    expect(isStaleChunkError(new Error("error loading dynamically imported module"))).toBe(true);
    expect(isStaleChunkError(new TypeError("Importing a module script failed."))).toBe(true);
    expect(isStaleChunkError(new Error("Request failed with status code 500"))).toBe(false);
  });

  it("recarrega na rota que a pessoa ia abrir, e só uma vez em 30 segundos", () => {
    const storage = memoria();
    const destinos = [];
    const location = { href: "https://app.starchef.com.br/", assign: (url) => destinos.push(url) };

    expect(reloadOnce("/pedidos", { storage, location, now: 1_000 })).toBe(true);
    // O erro voltou logo depois: não é versão velha, é outra coisa. Sem laço.
    expect(reloadOnce("/pedidos", { storage, location, now: 20_000 })).toBe(false);
    expect(reloadOnce("/pdv", { storage, location, now: 40_000 })).toBe(true);

    expect(destinos).toEqual(["/pedidos", "/pdv"]);
  });
});
