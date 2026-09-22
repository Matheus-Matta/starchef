import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import PdvVendaView from "./PdvVendaView.vue";
import { api } from "../services/api";

vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("../stores/auth", () => ({ useAuthStore: () => ({ user: { restaurant_id: "loja" } }) }));
vi.mock("../services/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

describe("abertura da página do PDV", () => {
  it("mostra catálogo e carrinho depois de carregar os dados", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data: { results: url.includes("products")
      ? [{ id: "produto", name: "Café", sale_price: "12.50", category: "bebidas" }]
      : [{ id: "bebidas", name: "Bebidas" }] } }));

    const tela = mount(PdvVendaView);

    await vi.waitFor(() => expect(tela.text()).toContain("Café"));
    expect(tela.text()).toContain("Pedido");
    expect(tela.text()).toContain("Incluir comanda");
  });
});
