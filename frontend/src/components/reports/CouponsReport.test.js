import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it, vi } from "vitest";

import CouponsReport from "./CouponsReport.vue";

const { getCouponRedemptions } = vi.hoisted(() => ({ getCouponRedemptions: vi.fn() }));
vi.mock("../../services/reportService", () => ({ reportService: { getCouponRedemptions } }));

const report = {
  totals: { uses: 3, discount: "23.01", net: "165.05", gross: "188.06" },
  by_coupon: [{ coupon_id: "c1", code: "DEZ", name: "Dez por cento", uses: 2, discount: "15.01", net: "135.05", gross: "150.06" }],
};

const montar = () =>
  mount(CouponsReport, {
    props: { report, filters: { date_from: "2026-10-01", date_to: "2026-10-31" } },
    global: {
      plugins: [PrimeVue],
      stubs: {
        ReportDataTable: {
          props: ["rows"],
          emits: ["row-click"],
          template: `<div><button v-for="row in rows" @click="$emit('row-click', row)">{{ row.code || row.order }} {{ row.document }}</button></div>`,
        },
      },
    },
  });

describe("CouponsReport", () => {
  it("mostra usos, descontado, vendido e líquido do período", () => {
    const text = montar().text();
    expect(text).toContain("Usos de cupom");
    expect(text).toContain("Total descontado");
    expect(text).toContain("23,01");
    expect(text).toContain("DEZ");
  });

  it("abre cada uso do cupom no mesmo período, com o CPF mascarado", async () => {
    getCouponRedemptions.mockResolvedValue({
      redemptions: [{ date: "2026-10-05T10:33:00-03:00", order_sequence: 413, document: "***.456.789-**", net: "90.00", discount: "10.00" }],
    });
    const wrapper = montar();
    await wrapper.find("button").trigger("click");
    await flushPromises();
    expect(getCouponRedemptions).toHaveBeenCalledWith("c1", { date_from: "2026-10-01", date_to: "2026-10-31" });
    expect(wrapper.text()).toContain("Usos do cupom DEZ");
    expect(wrapper.text()).toContain("#413");
    expect(wrapper.text()).toContain("***.456.789-**");
  });
});
