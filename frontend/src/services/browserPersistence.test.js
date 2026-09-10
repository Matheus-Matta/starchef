import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

async function loadPersistence({ production = false } = {}) {
  vi.resetModules();
  vi.stubEnv("PROD", production);
  return import("./browserPersistence");
}

describe("persistência do navegador", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("mantém localStorage somente no desenvolvimento", async () => {
    const { getBrowserValue, setBrowserValue } = await loadPersistence();

    setBrowserValue("starchef-theme", "dark");

    expect(getBrowserValue("starchef-theme")).toBe("dark");
    expect(localStorage.getItem("starchef-theme")).toBe("dark");
  });

  it("em produção grava cookie seguro e limpa o localStorage", async () => {
    localStorage.setItem("starchef-theme", "light");
    const cookieWrites = [];
    const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => "",
      set: (value) => {
        cookieWrites.push(value);
      },
    });

    try {
      const { setBrowserValue } = await loadPersistence({ production: true });
      setBrowserValue("starchef-theme", "dark");

      expect(localStorage.getItem("starchef-theme")).toBeNull();
      expect(cookieWrites).toHaveLength(1);
      expect(cookieWrites[0]).toContain("starchef-theme=dark");
      expect(cookieWrites[0]).toContain("Path=/");
      expect(cookieWrites[0]).toContain("SameSite=Lax");
      expect(cookieWrites[0]).toContain("Secure");
    } finally {
      delete document.cookie;
      if (descriptor) Object.defineProperty(Document.prototype, "cookie", descriptor);
    }
  });

  it("migra o valor legado para cookie durante a primeira leitura em produção", async () => {
    localStorage.setItem("starchef-restaurant-scope", "restaurant-1");
    const cookieWrites = [];
    const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => "",
      set: (value) => {
        cookieWrites.push(value);
      },
    });

    try {
      const { getBrowserValue } = await loadPersistence({ production: true });

      expect(getBrowserValue("starchef-restaurant-scope")).toBe("restaurant-1");
      expect(localStorage.getItem("starchef-restaurant-scope")).toBeNull();
      expect(cookieWrites[0]).toContain("starchef-restaurant-scope=restaurant-1");
    } finally {
      delete document.cookie;
      if (descriptor) Object.defineProperty(Document.prototype, "cookie", descriptor);
    }
  });
});
