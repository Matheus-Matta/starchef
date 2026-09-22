import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import KdsRulesEditor from "./KdsRulesEditor.vue";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({ api: { post: vi.fn() } }));

const station = { id: "station-1", rules: [], sectors: ["kitchen"], columns: [] };
const templates = [{ key: "cozinha", name: "Cozinha", sectors: ["kitchen"] }];

describe("regras de estações antigas", () => {
  it("mostra regras que a API já devolveu na estação", () => {
    const tela = mount(KdsRulesEditor, { props: {
      station: { ...station, rules: [{
        id: "receive-active", name: "Receber itens em produção", action: "include", enabled: true, conditions: [],
      }] },
      templates,
    } });

    expect(tela.text()).toContain("Receber itens em produção");
    expect(tela.find(".krules__defaults").exists()).toBe(false);
  });

  it("permite aplicar o modelo e exibe as regras devolvidas pela API", async () => {
    api.post.mockResolvedValue({ data: {
      ...station,
      rules: [{ id: "move-cancelled", name: "Mover itens cancelados", enabled: true, action: "move", conditions: [] }],
    } });
    const tela = mount(KdsRulesEditor, { props: { station, templates } });

    await tela.find(".krules__defaults button").trigger("click");
    await vi.waitFor(() => expect(tela.text()).toContain("Mover itens cancelados"));

    expect(api.post).toHaveBeenCalledWith("/kitchen/stations/station-1/apply-template-rules/", {
      template: "cozinha",
    });
    expect(tela.emitted("saved")).toHaveLength(1);
  });
});
