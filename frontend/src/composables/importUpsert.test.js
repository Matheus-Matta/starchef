import { describe, expect, it } from "vitest";

import { importKeyFor } from "./importUpsert";

const campos = [{ name: "name" }, { name: "internal_code" }, { name: "sale_price" }];

describe("importar CSV atualiza o que já existe", () => {
  it("prefere o código interno ao nome como chave", () => {
    expect(importKeyFor(campos)).toBe("internal_code");
    expect(importKeyFor([{ name: "name" }])).toBe("name");
  });

});
