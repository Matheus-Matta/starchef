import { beforeEach, describe, expect, it, vi } from "vitest";

// Dublê simples, e não `vi.fn`: o `vi.fn` guarda a promessa rejeitada no
// próprio histórico, e o Vitest acusava essa cópia como rejeição não tratada
// mesmo com a tela tratando o erro.
const chamadas = [];
let responder = async () => ({ data: {} });
vi.mock("../services/api", () => ({
  api: { post: (...args) => (chamadas.push(args), responder(...args)) },
}));

const { useInboundItemUnlink } = await import("./useInboundItemUnlink");

function montar() {
  const confirm = { require: vi.fn() };
  const toast = { add: vi.fn() };
  return { confirm, toast, ...useInboundItemUnlink({ confirm, toast }) };
}

describe("remover vínculo do item da NF-e", () => {
  beforeEach(() => {
    chamadas.length = 0;
  });

  it("só chama o backend depois da confirmação e recarrega a tela", async () => {
    responder = async () => ({ data: { message: "Vínculo removido." } });
    const onDone = vi.fn();
    const { confirm, unlinkInboundItem } = montar();

    unlinkInboundItem({ id: "item-1", description: "REFRI", product_name: "Guaraná" }, { onDone });

    expect(chamadas).toHaveLength(0);
    await confirm.require.mock.calls[0][0].accept();
    expect(chamadas).toEqual([["/inbound-nfe-items/item-1/unlink/"]]);
    expect(onDone).toHaveBeenCalled();
  });

  it("nota já recebida: mostra o motivo do backend e não recarrega", async () => {
    const recusa = Object.assign(new Error("409"), {
      response: { status: 409, data: { error: "Esta nota já entrou no estoque." } },
    });
    responder = async () => {
      throw recusa;
    };
    const onDone = vi.fn();
    const { confirm, toast, unlinkInboundItem } = montar();

    unlinkInboundItem({ id: "item-1", description: "REFRI" }, { onDone });
    await confirm.require.mock.calls[0][0].accept();

    expect(onDone).not.toHaveBeenCalled();
    expect(toast.add).toHaveBeenCalledWith(expect.objectContaining({ severity: "error" }));
  });
});
