import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ler = (arquivo) =>
  readFileSync(fileURLToPath(new URL(arquivo, import.meta.url)), "utf8");

/**
 * A linha do formulário só fica alinhada se TODO controle de uma linha tiver a
 * mesma altura. `min-height` não garante isso: cada componente do PrimeVue tem
 * o seu próprio padding interno, então o select parava mais alto que o campo
 * de texto e o calendário mais alto que os dois.
 */
describe("densidade dos formulários", () => {
  const compact = ler("./compact.css");
  const density = ler("./tokens/density.css");

  it("todo controle de uma linha usa a mesma altura", () => {
    const bloco = compact.slice(
      compact.indexOf(".p-dropdown,"),
      compact.indexOf(".p-calendar > .p-inputtext"),
    );
    for (const seletor of [
      ".p-dropdown",
      ".p-multiselect",
      ".p-calendar",
      ".p-password",
      ".p-inputnumber",
    ]) {
      expect(bloco).toContain(seletor);
    }
    // Altura fixa, não apenas um piso.
    expect(bloco).toContain("height: var(--control-h);");
    expect(bloco).not.toContain("min-height: var(--control-h);");
  });

  it("o campo de texto usa o mesmo token dos demais", () => {
    expect(compact).toMatch(/\.p-inputtext\s*\{[^}]*height:\s*var\(--control-h\)/);
  });

  it("a textarea continua crescendo com o texto", () => {
    // Travar a altura dela esconderia o que o operador acabou de escrever.
    expect(compact).toMatch(/textarea\.p-inputtext\s*\{[^}]*height:\s*auto/);
  });

  it("a altura vem de um token só", () => {
    expect(density).toMatch(/--control-h:\s*\d+px/);
  });
});
