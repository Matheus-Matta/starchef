import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it, vi } from "vitest";

import CashMovementsReport from "./CashMovementsReport.vue";
import OrdersCancellationsPanel from "./OrdersCancellationsPanel.vue";

// O Chart do PrimeVue precisa de canvas; aqui só interessa o que vira texto.
vi.mock("primevue/chart", () => ({ default: { name: "Chart", template: "<div class='chart-stub' />" } }));

const mountPanel = (component, report) =>
  mount(component, {
    props: { report, barOptions: {} },
    global: { plugins: [PrimeVue] },
  });

describe("CashMovementsReport", () => {
  it("mostra o resumo da gaveta e cada movimento com quem, onde e como", () => {
    const wrapper = mountPanel(CashMovementsReport, {
      summary: { cash_sales: "25.35", withdrawals: "30.00", supplies: "50.00", opening: "100.00", difference_total: "-10.00", sessions_with_difference: 1, sessions_count: 2, pending_count: 1, net: "145.35", change_given: "0", refunds: "0" },
      by_station: [{ cash_station_name: "Caixa 1", count: 3, supplies: "50.00", withdrawals: "30.00", total: "120.00" }],
      by_operator: [],
      by_day: [{ day: "2026-09-16", cash_sales: "25.35", withdrawals: "30.00", supplies: "50.00" }],
      sessions: [{ cash_station_name: "Caixa 1", operator_name: "Paulo", terminal_label: "Balcão 01", opened_at: "2026-09-16T11:00:00Z", closed_at: null, status: "open", expected_amount: "145.35", actual_amount: null, difference_amount: null }],
      movements: [{ id: "m1", created_at: "2026-09-16T12:00:00Z", cash_station_name: "Caixa 1", movement_type: "withdrawal", amount: "-30.00", reason: "Malote", destination: "Cofre", operator_name: "Paulo", terminal_label: "Balcão 01", authorization: "cash_password", authorized_by_name: "Paulo", order_sequence: null }],
    });
    const text = wrapper.text();
    expect(text).toContain("Vendas em dinheiro");
    expect(text).toContain("1 pendente(s) de autorização");
    expect(text).toContain("1 de 2 sessões com divergência");
    expect(text).toContain("Sangria");
    expect(text).toContain("Senha do caixa");
    expect(text).toContain("Balcão 01");
    expect(text).toContain("Aberto");
  });
});

describe("OrdersCancellationsPanel", () => {
  it("lista quem cancelou, quem liberou e os itens retirados", () => {
    const wrapper = mountPanel(OrdersCancellationsPanel, {
      orders_cancelled: 1,
      cancelled_total: "42.00",
      cancelled_rate: 12.5,
      voided_items_count: 1,
      voided_items_total: "7.50",
      cancelled_by_user: [{ name: "Ana", count: 1, total: "42.00" }],
      cancelled_by_hour: [{ hour: 20, count: 1, total: "42.00" }],
      cancelled_by_authorization: [{ label: "Senha do caixa", count: 1, total: "42.00" }],
      cancelled_orders: [{ id: "o1", sequence: 77, order_type_label: "Comanda", reference: "Comanda CMD-7", opened_at: "2026-09-16T20:00:00Z", cancelled_at: "2026-09-16T20:12:00Z", minutes_open: 12, cancelled_by: "Ana", authorization_label: "Senha do caixa", authorized_by: "", reason: "Cliente desistiu", items_count: 2, total: "42.00" }],
      voided_items: [{ id: "i1", order_sequence: 78, product_name: "Coxinha", quantity: 1, total_price: "7.50", kind: "Desistência", reason: "Trocou", voided_by: "Ana", voided_at: "2026-09-16T20:30:00Z", before_kitchen: true }],
    });
    const text = wrapper.text();
    expect(text).toContain("12,5%");
    expect(text).toContain("Ana");
    expect(text).toContain("Comanda CMD-7");
    expect(text).toContain("Cliente desistiu");
    expect(text).toContain("Coxinha");
    expect(text).toContain("Antes de enviar");
    expect(text).toContain("Senha do caixa");
  });
});
