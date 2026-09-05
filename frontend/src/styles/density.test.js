import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ler = (arquivo) =>
  readFileSync(fileURLToPath(new URL(arquivo, import.meta.url)), "utf8");

const compact = ler("./compact.css");
const density = ler("./tokens/density.css");
const shell = ler("../styles.css");

/**
 * A linha do formulário só fica alinhada se TODO controle de uma linha tiver a
 * mesma altura. Duas coisas precisam ser verdade, e as duas já falharam uma
 * vez: a regra tem de EXISTIR para cada tipo de campo, e tem de VENCER o tema
 * aura — que ganha de um seletor de classe simples.
 */
describe("densidade dos formulários", () => {
  /** O bloco de regras que fixa a altura dos controles. */
  const blocoDeAltura = () => {
    const inicio = compact.indexOf("html .p-inputtext,");
    expect(inicio, "o bloco de altura precisa existir").toBeGreaterThan(-1);
    return compact.slice(inicio, compact.indexOf("}", inicio));
  };

  it("cobre todo tipo de campo de uma linha", () => {
    const bloco = blocoDeAltura();
    for (const seletor of [
      ".p-inputtext",
      ".p-dropdown",
      ".p-multiselect",
      ".p-calendar",
      ".p-password",
      ".p-inputnumber",
    ]) {
      expect(bloco, `${seletor} ficou de fora`).toContain(`html ${seletor}`);
    }
  });

  it("usa o token, e não um número solto", () => {
    expect(blocoDeAltura()).toContain("height: var(--control-h)");
    expect(density).toMatch(/--control-h:\s*\d+px/);
  });

  it("vence o tema: toda regra de altura tem o prefixo html", () => {
    // Sem esta especificidade o CSS fica escrito e a tela continua
    // desalinhada — foi exatamente o que aconteceu na primeira tentativa.
    const seletores = blocoDeAltura()
      .split("{")[0]
      .split(",")
      .map((linha) => linha.trim())
      .filter(Boolean);
    expect(seletores.length).toBeGreaterThan(5);
    for (const seletor of seletores) {
      expect(seletor, `${seletor} sem prefixo html`).toMatch(/^html /);
    }
  });

  it("a textarea continua crescendo com o texto", () => {
    // Travar a altura dela esconderia o que o operador acabou de escrever.
    expect(compact).toMatch(
      /html textarea\.p-inputtext\s*\{[^}]*height:\s*auto/,
    );
  });

  it("a casca vive no mesmo arquivo dos outros tamanhos", () => {
    // Sidebar e topbar ficavam soltos no `styles.css`, fora do sistema:
    // reduzir os controles não mudava nada na tela. Dois donos para o mesmo
    // token também é armadilha — o de baixo vence, em silêncio.
    for (const token of ["--sidebar-w", "--sidebar-w-mini", "--topbar-h"]) {
      expect(density, `${token} precisa estar em density.css`).toContain(token);
      expect(shell, `${token} não pode ser redefinido em styles.css`).not.toContain(
        `${token}:`,
      );
    }
  });

  it("os tamanhos respondem ao tamanho da tela", () => {
    // Não é zoom: escalar a página inteira borra o texto e encolhe o alvo do
    // clique junto. Quem muda são os tokens.
    const degraus = density.match(/@media[^{]+\{\s*:root\s*\{/g) ?? [];
    expect(degraus.length, "faltam degraus de densidade").toBeGreaterThanOrEqual(2);
    expect(density).toMatch(/@media \(max-width: \d+px\)/);
    expect(density).toMatch(/@media \(min-width: \d+px\)/);
  });

  it("cada degrau redefine a altura do controle", () => {
    // Um degrau que não mexe em `--control-h` não muda nada de visível: foi
    // exatamente esse o sintoma antes — a regra existia e a tela não mudava.
    const blocos = density.split("@media").slice(1);
    expect(blocos.length).toBeGreaterThanOrEqual(2);
    for (const bloco of blocos) {
      expect(bloco).toMatch(/--control-h:\s*\d+px/);
      expect(bloco).toMatch(/--sidebar-w:\s*\d+px/);
    }
  });
});
