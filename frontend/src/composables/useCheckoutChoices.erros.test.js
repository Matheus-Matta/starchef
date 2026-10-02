import { nextTick, ref } from "vue";
import { describe, expect, it, vi } from "vitest";

// Cada chamada devolve uma promessa que o TESTE resolve, na ordem que quiser:
// é assim que se simula a rede entregando respostas fora de ordem.
const pendentes = [];
vi.mock("../services/api", () => ({
  api: { post: (url, corpo) => new Promise((resolve, reject) => pendentes.push({ url, corpo, resolve, reject })) },
}));

const { useCheckoutChoices } = await import("./useCheckoutChoices");

function montar() {
  const estado = {
    currentOrder: ref({ id: "p1", total: "50.00", service_fee_enabled: true }),
    discount: ref(0),
    discountInput: ref("0.00"),
    serviceFeeEnabled: ref(true),
    includeCpfOnInvoice: ref(false),
    invoiceCpf: ref(""),
    invoiceCpfError: ref(""),
  };
  const erros = [];
  return { estado, erros, escolhas: useCheckoutChoices(estado, { onErro: (e) => erros.push(e) }) };
}

describe("checkout com a rede falhando", () => {
  it("resposta velha que chega depois não sobrescreve a nova", async () => {
    pendentes.length = 0;
    const { estado, escolhas } = montar();

    estado.serviceFeeEnabled.value = false;
    const primeira = escolhas.salvar();          // taxa desligada
    estado.serviceFeeEnabled.value = true;
    const segunda = escolhas.salvar();           // taxa religada
    await nextTick();

    pendentes[1].resolve({ data: { id: "p1", total: "55.00", service_fee_enabled: true } });
    await segunda;
    pendentes[0].resolve({ data: { id: "p1", total: "50.00", service_fee_enabled: false } });
    await primeira;

    expect(estado.currentOrder.value.service_fee_enabled).toBe(true);
    expect(estado.currentOrder.value.total).toBe("55.00");
  });

  it("erro do servidor avisa a tela e não mexe no pedido", async () => {
    pendentes.length = 0;
    const { estado, erros, escolhas } = montar();

    const salvando = escolhas.salvar();
    pendentes[0].reject({ response: { status: 400, data: { error: { code: "invalid", message: "Desconto exige gerente." } } } });
    await salvando;

    expect(erros).toHaveLength(1);
    expect(estado.currentOrder.value.total).toBe("50.00");
  });

  it("queda de rede também avisa e não mexe no pedido", async () => {
    pendentes.length = 0;
    const { estado, erros, escolhas } = montar();

    const salvando = escolhas.salvar();
    pendentes[0].reject(new Error("Network Error"));
    await salvando;

    expect(erros).toHaveLength(1);
    expect(estado.currentOrder.value.id).toBe("p1");
  });

  it("trocou de pedido no meio: a resposta do pedido anterior não entra no atual", async () => {
    pendentes.length = 0;
    const { estado, escolhas } = montar();

    const salvando = escolhas.salvar();
    estado.currentOrder.value = { id: "p2", total: "10.00" };
    pendentes[0].resolve({ data: { id: "p1", total: "55.00" } });
    await salvando;

    expect(estado.currentOrder.value.id).toBe("p2");
  });
});
