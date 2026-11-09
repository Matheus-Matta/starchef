/**
 * Voltar devolve a tela na MESMA altura em que estava.
 *
 * Quem rola não é a janela, é a `<section class="app-content">` do layout —
 * por isso o `scrollBehavior` do vue-router não serviria. A altura de cada
 * endereço é guardada ao sair; ao voltar (botão Voltar/Avançar do navegador),
 * ela é devolvida. Navegar para uma tela nova começa do topo.
 *
 * A lista pode chegar depois da animação (sem cache, espera a rede): por isso
 * a devolução tenta de novo, quadro a quadro, até a página ter altura para
 * chegar lá — ou desiste em 1,5 s.
 */
const ESPERA_MAXIMA_MS = 1500;

export function useScrollMemory({ router, elemento, agora = () => performance.now() }) {
  const alturas = new Map();
  let voltando = false;
  let destino = null;

  const marcarVolta = () => { voltando = true; };
  window.addEventListener("popstate", marcarVolta);

  const tirarAntes = router.beforeEach((to, from) => {
    if (elemento.value && to.path !== from.path) alturas.set(from.fullPath, elemento.value.scrollTop);
  });

  const tirarDepois = router.afterEach((to, from) => {
    // Mesma tela com outra query (filtro, página da lista): a tela não remonta, nada a fazer.
    if (to.path === from.path) {
      voltando = false;
      return;
    }
    destino = voltando ? alturas.get(to.fullPath) ?? 0 : 0;
    voltando = false;
  });

  /** Chamado quando a tela nova terminou de entrar (`@after-enter` da Transition). */
  function aoEntrar() {
    const el = elemento.value;
    if (!el || destino === null) return;
    const alvo = destino;
    destino = null;
    const inicio = agora();
    const tentar = () => {
      el.scrollTop = alvo;
      const chegou = Math.abs(el.scrollTop - alvo) < 2;
      if (!chegou && agora() - inicio < ESPERA_MAXIMA_MS) requestAnimationFrame(tentar);
    };
    tentar();
  }

  const parar = () => {
    window.removeEventListener("popstate", marcarVolta);
    tirarAntes();
    tirarDepois();
  };
  return { aoEntrar, parar };
}
