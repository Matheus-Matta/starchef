import { describe, expect, it } from "vitest";
import { nextTick, reactive, ref } from "vue";

import { useListUrlState } from "./useListUrlState";

// Filtrar "notas com erro, página 3", abrir uma nota e voltar caía na página 1
// sem filtro: o estado da lista morava só na memória da tela.
function rotaFalsa(query = {}) {
  const route = reactive({ name: "notas-fiscais", query });
  const router = { replace: ({ query: nova }) => { route.query = nova; return Promise.resolve(); } };
  return { route, router };
}

function campos({ page, busca, filtros }) {
  return [
    { chave: "pagina", ler: () => (page.value > 1 ? String(page.value) : ""), escrever: (v) => { page.value = Number(v) || 1; } },
    { chave: "busca", ler: () => busca.value, escrever: (v) => { busca.value = v; } },
    { prefixo: "f_", ler: () => filtros, escrever: (valores) => Object.assign(filtros, valores) },
  ];
}

describe("useListUrlState", () => {
  it("o estado da tela vai para a URL, sem apagar os outros parâmetros", async () => {
    const { route, router } = rotaFalsa({ status: "error" });
    const estado = { page: ref(1), busca: ref(""), filtros: reactive({}) };
    useListUrlState({ route, router, campos: campos(estado) });

    estado.page.value = 3;
    estado.busca.value = "joão";
    estado.filtros.payment_status = "paid";
    await nextTick();

    expect(route.query).toEqual({ status: "error", pagina: "3", busca: "joão", f_payment_status: "paid" });
  });

  it("voltar para a URL restaura página, busca e filtros", () => {
    const { route, router } = rotaFalsa({ pagina: "3", busca: "joão", f_payment_status: "paid" });
    const estado = { page: ref(1), busca: ref(""), filtros: reactive({}) };

    const url = useListUrlState({ route, router, campos: campos(estado) });

    expect(url.restaurou).toBe(true);
    expect(estado.page.value).toBe(3);
    expect(estado.busca.value).toBe("joão");
    expect(estado.filtros).toEqual({ payment_status: "paid" });
  });

  it("valor vazio ou padrão sai da URL", async () => {
    const { route, router } = rotaFalsa({ pagina: "2", busca: "x" });
    const estado = { page: ref(1), busca: ref(""), filtros: reactive({}) };
    useListUrlState({ route, router, campos: campos(estado) });

    estado.page.value = 1;
    estado.busca.value = "";
    await nextTick();

    expect(route.query).toEqual({});
  });

  it("fora da própria rota não escreve nada (a tela está saindo)", async () => {
    const { route, router } = rotaFalsa();
    const estado = { page: ref(1), busca: ref(""), filtros: reactive({}) };
    useListUrlState({ route, router, campos: campos(estado) });

    route.name = "notas-fiscais--view";
    estado.page.value = 5;
    await nextTick();

    expect(route.query).toEqual({});
  });
});
