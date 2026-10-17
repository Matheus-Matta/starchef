import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

import { api } from "../services/api";
import { useDanfePrintQuestion } from "./useDanfePrintQuestion";

const ligado = { ask_print_danfe: true };
const pedido = { id: "p1", sequence: 7 };

function janela() {
  return { document: { write: vi.fn(), open: vi.fn(), close: vi.fn() }, focus: vi.fn(), print: vi.fn(), close: vi.fn() };
}

function montar(win = janela()) {
  const toast = { add: vi.fn() };
  const danfe = useDanfePrintQuestion({ toast, sleep: () => Promise.resolve(), openWindow: () => win });
  return { danfe, toast, win };
}

const comNota = (fiscal) => api.get.mockResolvedValue({ data: { sequence: 7, fiscal } });

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
});

describe("useDanfePrintQuestion", () => {
  it("restaurante sem a chave não pergunta nem consulta o pedido", async () => {
    const { danfe } = montar();
    await danfe.oferecer(pedido, { ask_print_danfe: false });
    expect(danfe.pergunta.value).toBeNull();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("pedido sem nota (loja que não emite) não pergunta", async () => {
    comNota(null);
    const { danfe } = montar();
    await danfe.oferecer(pedido, ligado);
    expect(danfe.pergunta.value).toBeNull();
  });

  it("nota recusada não pergunta: não há o que imprimir", async () => {
    comNota({ id: "n1", printable: false, fiscal_state: "rejected" });
    const { danfe } = montar();
    await danfe.oferecer(pedido, ligado);
    expect(danfe.pergunta.value).toBeNull();
  });

  it("cancelar fecha a pergunta e não imprime nada", async () => {
    comNota({ id: "n1", printable: true, fiscal_state: "authorized", number: 12 });
    const { danfe, win } = montar();
    await danfe.oferecer(pedido, ligado);
    expect(danfe.pergunta.value.summary).toBe("Pedido #7 · NFC-e 12");
    danfe.cancelar();
    expect(danfe.pergunta.value).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    expect(win.print).not.toHaveBeenCalled();
  });

  it("nota autorizada: imprimir gera o DANFE e abre a impressão", async () => {
    comNota({ id: "n1", printable: true, fiscal_state: "authorized", number: 12 });
    api.post.mockResolvedValue({ data: { html: "<p>DANFE</p>" } });
    const { danfe, win } = montar();
    await danfe.oferecer(pedido, ligado);
    await danfe.imprimir();
    expect(api.post).toHaveBeenCalledWith("/invoices/n1/print/", {});
    expect(win.document.write).toHaveBeenLastCalledWith("<p>DANFE</p>");
    expect(win.print).toHaveBeenCalled();
  });

  it("nota a caminho: espera a SEFAZ autorizar e só então imprime", async () => {
    comNota({ id: "n1", printable: false, fiscal_state: "processing" });
    api.post
      .mockResolvedValueOnce({ data: { printable: false, fiscal_state: "processing" } })
      .mockResolvedValueOnce({ data: { printable: true, fiscal_state: "authorized" } })
      .mockResolvedValueOnce({ data: { html: "<p>DANFE</p>" } });
    const { danfe, win } = montar();
    await danfe.oferecer(pedido, ligado);
    await danfe.imprimir();
    expect(api.post).toHaveBeenNthCalledWith(1, "/invoices/n1/refresh-status/", { manual_print: true });
    expect(api.post).toHaveBeenLastCalledWith("/invoices/n1/print/", {});
    expect(win.print).toHaveBeenCalled();
  });

  it("a SEFAZ recusa durante a espera: fecha a janela e avisa", async () => {
    comNota({ id: "n1", printable: false, fiscal_state: "processing" });
    api.post.mockResolvedValue({ data: { printable: false, fiscal_state: "rejected" } });
    const { danfe, win, toast } = montar();
    await danfe.oferecer(pedido, ligado);
    await danfe.imprimir();
    expect(win.close).toHaveBeenCalled();
    expect(win.print).not.toHaveBeenCalled();
    expect(toast.add).toHaveBeenCalled();
  });
});
