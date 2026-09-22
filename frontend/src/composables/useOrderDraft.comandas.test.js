import { describe, expect, it } from "vitest";

import { useOrderDraft } from "./useOrderDraft";

/**
 * O carrinho mostra a conta INTEIRA: o que foi passado agora e o que as
 * comandas já tinham anotado.
 *
 * Antes só os itens novos apareciam. O operador anexava quatro cartões e via
 * um carrinho vazio com um total que não batia com nada na tela — e só
 * descobria o que estava cobrando depois de abrir a conta.
 */
const COMANDA = { id: "c-1", number: 12 };
const ANOTACAO = { id: "i-1", product_name: "Pastel", quantity: 1, unit_price: "10.00" };

function comCartaoAnexado() {
  const rascunho = useOrderDraft();
  rascunho.anexarComanda(COMANDA);
  rascunho.registrarItensDaComanda("c-1", [ANOTACAO]);
  return rascunho;
}

describe("useOrderDraft — comandas no carrinho", () => {
  it("as anotacoes da comanda aparecem no carrinho", () => {
    const rascunho = comCartaoAnexado();

    expect(rascunho.itensVisiveis.value).toHaveLength(1);
    expect(rascunho.itensVisiveis.value[0].product_name).toBe("Pastel");
  });

  it("cada anotacao diz de qual comanda veio", () => {
    const rascunho = comCartaoAnexado();

    expect(rascunho.itensVisiveis.value[0].command_number).toBe(12);
  });

  it("as anotacoes vem ANTES do que foi passado agora", () => {
    // O que já estava no cartão é o contexto; o que o operador acabou de
    // passar é o que ele está conferindo. Inverter faria a linha nova sumir
    // no meio de uma conta grande.
    const rascunho = comCartaoAnexado();
    rascunho.adicionar({ id: "p-9", name: "Coxinha", sale_price: "6.00" });

    const nomes = rascunho.itensVisiveis.value.map((i) => i.product_name);
    expect(nomes[0]).toBe("Pastel");
  });

  it("o total soma os dois grupos", () => {
    const rascunho = comCartaoAnexado();
    rascunho.adicionar({ id: "p-9", name: "Coxinha", sale_price: "6.00" });

    expect(rascunho.total.value).toBe(16);
  });

  it("retirar a comanda tira as anotacoes dela do carrinho", () => {
    const rascunho = comCartaoAnexado();

    rascunho.soltarComanda("c-1");

    expect(rascunho.itensVisiveis.value).toHaveLength(0);
  });

  it("carrinho sem nada continua vazio", () => {
    const rascunho = useOrderDraft();

    expect(rascunho.vazio.value).toBe(true);
  });

  it("comanda anexada SEM anotacoes lidas nao quebra", () => {
    // A prévia pode falhar (rede), e o carrinho tem de seguir utilizável:
    // quem monta a conta de verdade é o servidor, no `attach-commands`.
    const rascunho = useOrderDraft();
    rascunho.anexarComanda(COMANDA);

    expect(rascunho.itensVisiveis.value).toEqual([]);
  });
});
