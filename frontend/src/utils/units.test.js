import { describe, expect, it } from "vitest";

import { convertUnit, dimensionOf } from "./units";

/**
 * Esta tabela é um espelho de `backend/apps/menu/units.py`. Se as duas se
 * desencontrarem, a prévia da tela ("vai somar 10.000 g") passa a mentir sobre
 * o que o backend realmente vai gravar — que é justamente o erro de cadastro
 * que a prévia existe para evitar.
 */
describe("convertUnit", () => {
  it("converte peso entre kg e g", () => {
    expect(convertUnit(0.03, "kg", "g")).toBe(30);
    expect(convertUnit(2500, "g", "kg")).toBe(2.5);
  });

  it("converte volume entre l e ml", () => {
    expect(convertUnit(1, "l", "ml")).toBe(1000);
    expect(convertUnit(1500, "ml", "l")).toBe(1.5);
  });

  it("devolve a mesma quantidade quando a unidade não muda", () => {
    expect(convertUnit(7, "unit", "unit")).toBe(7);
    expect(convertUnit(42, "g", "g")).toBe(42);
  });

  it("recusa conversão entre grandezas diferentes", () => {
    // Litro para grama depende da densidade do conteúdo.
    expect(convertUnit(1, "l", "g")).toBeNull();
    expect(convertUnit(1, "unit", "kg")).toBeNull();
  });

  it("recusa unidade desconhecida", () => {
    expect(convertUnit(1, "duzia", "unit")).toBeNull();
    expect(convertUnit(1, "g", "arroba")).toBeNull();
  });

  it("recusa quantidade que não é número", () => {
    expect(convertUnit("abc", "kg", "g")).toBeNull();
  });

  it("trata campo vazio como ausente, não como zero", () => {
    // `Number(null)` e `Number("")` valem 0: sem a guarda, um campo em branco
    // exibiria "0 g" como se fosse um valor já calculado.
    expect(convertUnit(null, "kg", "g")).toBeNull();
    expect(convertUnit(undefined, "kg", "g")).toBeNull();
    expect(convertUnit("", "kg", "g")).toBeNull();
    expect(convertUnit(0, "kg", "g")).toBe(0);
  });

  it("classifica a grandeza de cada unidade", () => {
    expect(dimensionOf("kg")).toBe("weight");
    expect(dimensionOf("ml")).toBe("volume");
    expect(dimensionOf("unit")).toBe("count");
    expect(dimensionOf("duzia")).toBeNull();
  });

  it("2 pacotes de 5 kg viram 10.000 g", () => {
    // O mesmo exemplo da seção 7 do plano de estoque.
    expect(convertUnit(2 * 5, "kg", "g")).toBe(10000);
  });
});
