import { mount, RouterLinkStub } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ResourceDetailField from "./ResourceDetailField.vue";

describe("detalhe de recurso", () => {
  it("mostra o numero do pedido como link para o pedido", () => {
    const wrapper = mount(ResourceDetailField, {
      props: {
        field: { key: "order_sequence", label: "Pedido", type: "order-link", idKey: "order", _value: 42 },
        record: { order: "order-id" },
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });

    expect(wrapper.text()).toContain("Pedido #42");
    expect(wrapper.getComponent(RouterLinkStub).props("to")).toEqual({
      name: "pedidos--view",
      params: { id: "order-id" },
    });
  });
});
