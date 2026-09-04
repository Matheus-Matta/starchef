/**
 * @vitest-environment jsdom
 * @vitest-environment-options { "url": "https://app.starchef.com.br/" }
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { clearSession } from "./tokenStorage";

describe("clearSession", () => {
  let written;
  let descriptor;

  beforeEach(() => {
    written = [];
    descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => "",
      set: (value) => {
        written.push(value);
      },
    });
  });

  afterEach(() => {
    delete document.cookie;
    if (descriptor) Object.defineProperty(Document.prototype, "cookie", descriptor);
  });

  // O backend grava a flag com Domain quando a API vive em outro subdomínio
  // (DJANGO_AUTH_COOKIE_DOMAIN): sem repetir o Domain, o delete não casa e o
  // usuário continua "logado" depois de clicar em Sair.
  it("expira a flag no host e nos domínios-pai", () => {
    clearSession();

    expect(written).toContain("sc_session=; Max-Age=0; path=/");
    expect(written.some((c) => c.endsWith("; domain=app.starchef.com.br"))).toBe(true);
    expect(written.some((c) => c.endsWith("; domain=starchef.com.br"))).toBe(true);
    expect(written.some((c) => c.endsWith("; domain=.starchef.com.br"))).toBe(true);
  });
});
