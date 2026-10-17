import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import SalesHeatmap from "./SalesHeatmap.vue";

const cells = (overrides) =>
  Array.from({ length: 24 }, (_, hour) => ({
    hour, command_items: 0, command_total: "0.00", counter_items: 0, counter_total: "0.00",
    ...(overrides[hour] || {}),
  }));

const heatmap = {
  mode: "day",
  rows: [{
    key: "2026-10-14",
    label: "Quarta",
    cells: cells({
      9: { counter_items: 1, counter_total: "10.00" },
      12: { command_items: 4, command_total: "40.00" },
    }),
  }],
};

const levelAt = (wrapper, hour) =>
  wrapper.findAll(".sales-heatmap__grid .sales-heatmap__cell")[hour].attributes("data-level");

describe("SalesHeatmap", () => {
  it("pinta o pico mais forte e mostra comanda e balcão no tooltip", () => {
    const wrapper = mount(SalesHeatmap, { props: { heatmap } });

    expect(wrapper.text()).toContain("14/10");
    expect(levelAt(wrapper, 12)).toBe("4");
    expect(levelAt(wrapper, 9)).toBe("1");
    expect(levelAt(wrapper, 3)).toBe("0");
    const tip = wrapper.findAll(".sales-heatmap__grid .sales-heatmap__cell")[12].attributes("title");
    expect(tip).toContain("Comanda: 4 itens (R$");
    expect(tip).toContain("Balcão: 0 itens");
  });

  it("filtrar só balcão faz o horário do balcão virar o pico", async () => {
    const wrapper = mount(SalesHeatmap, { props: { heatmap } });

    await wrapper.findAll("button").find((b) => b.text() === "Balcão").trigger("click");

    expect(levelAt(wrapper, 9)).toBe("4");
    expect(levelAt(wrapper, 12)).toBe("0");
  });
});
