import { mount } from "@vue/test-utils";
import { ref } from "vue";
import { describe, expect, it } from "vitest";

import StatCard from "./StatCard.vue";

// O valor do relatório que mudou pelo tempo real sobe na tela; o que mudou
// porque a pessoa trocou o filtro, não.
const montar = (live) =>
  mount(StatCard, {
    props: { label: "Total vendido", value: "R$ 10,00" },
    global: { provide: { statCardLive: live } },
  });

describe("StatCard", () => {
  it("anima o valor que mudou pelo tempo real", async () => {
    const live = ref(true);
    const card = montar(live);

    await card.setProps({ value: "R$ 25,00" });

    expect(card.find(".sc-stat-card__value").classes()).toContain("sc-stat-card__value--rise");
    expect(card.text()).toContain("R$ 25,00");
  });

  it("valor trocado pelo filtro não anima", async () => {
    const card = montar(ref(false));

    await card.setProps({ value: "R$ 25,00" });

    expect(card.find(".sc-stat-card__value").classes()).not.toContain("sc-stat-card__value--rise");
  });
});
