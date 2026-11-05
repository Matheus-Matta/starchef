import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const component = readFileSync(resolve("src/components/stock/StockLabelSheet.vue"), "utf8");

describe("etiqueta de estoque", () => {
  it("deixa os dados a esquerda e o codigo de barras a direita sem repetir o codigo em texto", () => {
    expect(component).toContain('class="labelsheet__text"');
    expect(component).toContain('class="labelsheet__code-img"');
    expect(component).not.toContain("{{ label.code }}");
    expect(component).toMatch(/\.labelsheet__item\s*\{[^}]*display:\s*flex/);
  });

  it("mostra a validade somente quando ela existe", () => {
    expect(component).toContain("show('show_expires_at') && label.expires_at");
  });
});
