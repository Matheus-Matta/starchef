import { describe, expect, it } from "vitest";

import {
  CASH_STATUS_LABELS,
  GOODS_RECEIPT_STATUS_LABELS,
  INVENTORY_LOT_STATUS_LABELS,
  MOVEMENT_TYPE_LABELS,
  PAYMENT_STATUS_LABELS,
} from "./enums";
import { PAYMENT_DETAIL_LABELS } from "./cashLabels";
import { detailMetaFor } from "./detailMeta";
import { resources } from "./resources";
import { normalizeApiError } from "../utils/apiError";

describe("traduções de status vindos do backend", () => {
  it("cobre os valores atuais de estoque e recebimento", () => {
    expect(MOVEMENT_TYPE_LABELS.SALE_OUTPUT).toBe("Saída por venda");
    expect(MOVEMENT_TYPE_LABELS.PRODUCTION_CONSUMPTION).toBe("Consumo em ficha técnica");
    expect(INVENTORY_LOT_STATUS_LABELS.ACTIVE.label).toBe("Ativo / Disponível");
    expect(INVENTORY_LOT_STATUS_LABELS.CONSUMED.label).toBe("Esgotado");
    expect(GOODS_RECEIPT_STATUS_LABELS.CONFIRMED.label).toBe("Confirmado");
    expect(GOODS_RECEIPT_STATUS_LABELS.CANCELLED.label).toBe("Cancelado");
  });

  it("traduz cancelamento de pagamento e a fase da nota fiscal", () => {
    expect(PAYMENT_STATUS_LABELS.cancelled).toBe("Cancelado");
    const invoices = resources.find((resource) => resource.name === "notas-fiscais");
    const phase = invoices.columns.find((column) => column.key === "phase");
    expect(phase.map.receipt).toBe("Comprovante");
    expect(phase.map.fiscal).toBe("Fiscal");
  });

  it("traduz estados do caixa e tipos de cartão", () => {
    expect(CASH_STATUS_LABELS.pending_opening).toBe("Aguardando abertura");
    expect(CASH_STATUS_LABELS.pending_closing).toBe("Aguardando fechamento");
    expect(PAYMENT_DETAIL_LABELS.credit).toBe("Crédito");
    expect(PAYMENT_DETAIL_LABELS.debit).toBe("Débito");
  });

  it("entrega texto, e não o objeto de configuração, no selo do detalhe", () => {
    const meta = detailMetaFor("/inbound-nfe/");
    expect(meta.badge({ status: "received" })).toBe("Entrada Concluída");
  });
});

describe("traduções de mensagens padrão da API", () => {
  it("não mostra a frase inglesa do DRF", () => {
    const error = { response: { status: 404, data: { detail: "Not found." } } };
    expect(normalizeApiError(error).message).toBe("Registro não encontrado.");
  });

  it("traduz validação de campo obrigatório", () => {
    const error = { response: { status: 400, data: { name: ["This field is required."] } } };
    expect(normalizeApiError(error).fieldErrors.name).toBe("Este campo é obrigatório.");
  });
});
