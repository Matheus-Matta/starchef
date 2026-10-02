import { nextTick, ref } from "vue";
import { describe, expect, it, vi } from "vitest";

const chamadas = [];
vi.mock("../services/api", () => ({
  api: { post: async (url, corpo) => (chamadas.push([url, corpo]), { data: { id: "p1", total: "55.00" } }) },
}));

const { useCheckoutChoices } = await import("./useCheckoutChoices");

function montar(pedido) {
  const estado = {
    currentOrder: ref(pedido),
    discount: ref(0),
    discountInput: ref("0.00"),
    serviceFeeEnabled: ref(true),
    includeCpfOnInvoice: ref(false),
    invoiceCpf: ref(""),
    invoiceCpfError: ref(""),
  };
  return { estado, escolhas: useCheckoutChoices(estado) };
}

describe("escolhas do checkout", () => {
  it("restaura taxa, desconto e CPF gravados no pedido", () => {
    const { estado, escolhas } = montar(null);

    escolhas.restaurar({ id: "p1", discount: "2.50", service_fee_enabled: false, fiscal_customer_cpf: "52998224725" });

    expect(estado.serviceFeeEnabled.value).toBe(false);
    expect(estado.discountInput.value).toBe("2.50");
    expect(estado.includeCpfOnInvoice.value).toBe(true);
    expect(estado.invoiceCpf.value).toBe("529.982.247-25");
  });

  it("restaurar não grava nada no servidor", async () => {
    const antes = chamadas.length;
    const { escolhas } = montar({ id: "p1" });

    escolhas.restaurar({ id: "p1", service_fee_enabled: false });
    await escolhas.salvar();

    expect(chamadas.length).toBe(antes);
  });

  it("grava pelo /checkout/ com taxa e CPF", async () => {
    const { estado, escolhas } = montar({ id: "p1" });
    estado.includeCpfOnInvoice.value = true;
    estado.invoiceCpf.value = "529.982.247-25";
    await nextTick();

    await escolhas.salvar();

    expect(chamadas.at(-1)).toEqual([
      "/orders/p1/checkout/",
      { discount: 0, service_fee_enabled: true, fiscal_customer_cpf: "52998224725" },
    ]);
  });

  it("CPF incompleto não vai ao servidor e mostra o erro", async () => {
    const antes = chamadas.length;
    const { estado, escolhas } = montar({ id: "p1" });
    estado.includeCpfOnInvoice.value = true;
    estado.invoiceCpf.value = "529.982";
    await nextTick();

    await escolhas.salvar();

    expect(chamadas.length).toBe(antes);
    expect(escolhas.documento().erro).toBe("Informe um CPF válido.");
  });

  it("CNPJ só aparece quando o servidor já o conhece", () => {
    expect(montar({ id: "p1" }).escolhas.cnpjDisponivel.value).toBe(false);
    expect(montar({ id: "p1", fiscal_customer_cnpj: "" }).escolhas.cnpjDisponivel.value).toBe(true);
  });

  it("CPF e CNPJ são um ou outro", () => {
    const { estado, escolhas } = montar({ id: "p1", fiscal_customer_cnpj: "" });
    estado.includeCpfOnInvoice.value = true;

    escolhas.includeCnpjOnInvoice.value = true;
    escolhas.alternarDocumento("cnpj");

    expect(estado.includeCpfOnInvoice.value).toBe(false);
  });

  it("CNPJ válido vai no corpo, e o CPF vai vazio", async () => {
    const { escolhas } = montar({ id: "p1", fiscal_customer_cnpj: "" });
    escolhas.includeCnpjOnInvoice.value = true;
    escolhas.invoiceCnpj.value = "11.222.333/0001-81";
    await nextTick();

    expect(escolhas.corpo()).toMatchObject({ fiscal_customer_cpf: "", fiscal_customer_cnpj: "11222333000181" });
  });
});
