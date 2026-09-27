import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import PermissionAccordion from "./PermissionAccordion.vue";

describe("PermissionAccordion", () => {
  it("inicia todos os grupos abertos no formulario", () => {
    const wrapper = mount(PermissionAccordion, {
      props: {
        groups: [
          { label: "Pedidos", items: [] },
          { label: "Estoque", items: [] },
          { label: "Financeiro", items: [] },
        ],
      },
    });

    const groups = wrapper.findAll("details");
    expect(groups).toHaveLength(3);
    expect(groups.every((group) => group.attributes("open") !== undefined)).toBe(true);
  });
});
