import { describe, expect, it } from "vitest";
import { ref } from "vue";

import { useScrollMemory } from "./useScrollMemory";

// Voltar de um registro devolvia a lista no topo: quem rola é a `app-content`
// do layout, e o vue-router só sabe devolver a rolagem da janela.
function roteadorFalso() {
  const antes = [];
  const depois = [];
  return {
    beforeEach: (fn) => { antes.push(fn); return () => {}; },
    afterEach: (fn) => { depois.push(fn); return () => {}; },
    ir(from, to, { voltar = false } = {}) {
      if (voltar) window.dispatchEvent(new PopStateEvent("popstate"));
      antes.forEach((fn) => fn(to, from));
      depois.forEach((fn) => fn(to, from));
    },
  };
}

const rota = (fullPath) => ({ path: fullPath.split("?")[0], fullPath });

describe("useScrollMemory", () => {
  it("voltar devolve a altura em que a lista estava", () => {
    const router = roteadorFalso();
    const elemento = ref({ scrollTop: 0 });
    const memoria = useScrollMemory({ router, elemento });

    elemento.value.scrollTop = 800;
    router.ir(rota("/notas-fiscais?pagina=3"), rota("/notas-fiscais/1"));
    memoria.aoEntrar();
    expect(elemento.value.scrollTop).toBe(0);  // tela nova começa do topo

    router.ir(rota("/notas-fiscais/1"), rota("/notas-fiscais?pagina=3"), { voltar: true });
    memoria.aoEntrar();
    expect(elemento.value.scrollTop).toBe(800);
    memoria.parar();
  });

  it("mudar só a query (filtro, página) não mexe na rolagem", () => {
    const router = roteadorFalso();
    const elemento = ref({ scrollTop: 500 });
    const memoria = useScrollMemory({ router, elemento });

    router.ir(rota("/notas-fiscais"), rota("/notas-fiscais?busca=jo"));
    memoria.aoEntrar();

    expect(elemento.value.scrollTop).toBe(500);
    memoria.parar();
  });
});
