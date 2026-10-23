import { describe, expect, it } from "vitest";
import { recusaDoTroco } from "./trocoSoEmDinheiro";

// O troco de cartão sai da gaveta sem nada ter entrado nela: um de R$ 50 num
// débito deixou a nuvem R$ 50 acima da loja. O restaurante pode desligar.
const desligado = { allow_change_on_non_cash: false };
const debito = { name: "Cartão de débito", method_type: "card" };

describe("troco só em dinheiro", () => {
  it("desligado, o débito acima do restante é recusado com o máximo", () => {
    expect(recusaDoTroco({ restaurante: desligado, forma: debito, recebido: 100, restante: 50 }))
      .toBe("Este restaurante dá troco só em dinheiro: em Cartão de débito, receba no máximo R$ 50,00.");
  });

  it("desligado, o valor exato passa e o dinheiro continua dando troco", () => {
    expect(recusaDoTroco({ restaurante: desligado, forma: debito, recebido: 50, restante: 50 })).toBe("");
    expect(recusaDoTroco({ restaurante: desligado, forma: { name: "Dinheiro", method_type: "cash" }, recebido: 100, restante: 50 })).toBe("");
  });

  it("ligado (ou restaurante antigo, sem o campo), o débito dá troco como antes", () => {
    expect(recusaDoTroco({ restaurante: { allow_change_on_non_cash: true }, forma: debito, recebido: 100, restante: 50 })).toBe("");
    expect(recusaDoTroco({ restaurante: {}, forma: debito, recebido: 100, restante: 50 })).toBe("");
  });
});
