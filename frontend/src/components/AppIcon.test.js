import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import AppIcon from "./AppIcon.vue";

describe("AppIcon", () => {
  it("renderiza o ícone mapeado e é decorativo sem label", () => {
    const wrapper = mount(AppIcon, { props: { name: "check" } });
    expect(wrapper.find("i").classes()).toContain("pi-check");
    expect(wrapper.find("i").attributes("aria-hidden")).toBe("true");
  });

  it("cai no ícone padrão quando o nome não existe no mapa", () => {
    const wrapper = mount(AppIcon, { props: { name: "nao-existe" } });
    expect(wrapper.find("i").classes()).toContain("pi-circle");
  });

  it("fica acessível (role=img + aria-label) quando recebe um label", () => {
    const wrapper = mount(AppIcon, { props: { name: "bell", label: "Notificações" } });
    const icon = wrapper.find("i");
    expect(icon.attributes("role")).toBe("img");
    expect(icon.attributes("aria-label")).toBe("Notificações");
  });
});
