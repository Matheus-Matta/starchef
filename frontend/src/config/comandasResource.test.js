import { describe, expect, it } from "vitest";
import { resources } from "./resources";

// O status da comanda é calculado: pelo `filter__status` genérico a API
// ignorava o filtro e a lista vinha inteira.
describe("lista de comandas", () => {
  const comandas = resources.find((resource) => resource.name === "comandas");

  it("filtra status e situação pelo parâmetro que a API conhece", () => {
    const porNome = Object.fromEntries(comandas.pro.filterFields.map((field) => [field.name, field]));
    expect(porNome.status.param).toBe("status");
    expect(porNome.status.options.map((option) => option.value)).toEqual(["free", "occupied"]);
    expect(porNome.is_active.param).toBe("is_active");
    expect(comandas.pro.filterFields.every((field) => field.compact)).toBe(true);
  });

  it("o Mais filtros traz filtros, não o formulário de cadastro", () => {
    const labels = comandas.pro.advancedFilters.map((field) => field.label);
    expect(labels).toEqual(["Comanda de", "Comanda até", "Cliente", "Código"]);
    expect(labels.some((label) => label.includes("(opcional)"))).toBe(false);
  });
});
