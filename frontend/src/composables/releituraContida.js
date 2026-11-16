// No máximo UMA releitura por `intervalo`, e sempre uma última depois que os
// pedidos param. Com a aba escondida, nenhuma: a releitura fica devida e sai
// quando a aba volta.
//
// Cada pedido, item ou pagamento salvo em qualquer caixa avisa todas as telas
// abertas da loja. O resumo do topo do painel (em TODA aba aberta, em qualquer
// página), o quadro do KDS e o relatório reliam a cada aviso — dezenas de
// leituras pesadas por venda, multiplicadas pelo número de telas. Era isso que
// mantinha o servidor da loja em 100% de CPU com cinco máquinas.
export function releituraContida(carregar, { intervalo = 10000, agora = () => Date.now() } = {}) {
  let ultima = -Infinity;
  let adiada = null;
  let devidaNaVolta = false;

  const oculta = () => typeof document !== "undefined" && document.hidden;

  function executar() {
    ultima = agora();
    carregar();
  }

  function pedir() {
    if (oculta()) {
      devidaNaVolta = true;
      return;
    }
    const espera = ultima + intervalo - agora();
    if (espera <= 0) {
      executar();
      return;
    }
    if (!adiada) {
      adiada = setTimeout(() => {
        adiada = null;
        if (oculta()) {
          devidaNaVolta = true;
          return;
        }
        executar();
      }, espera);
    }
  }

  function aoMudarVisibilidade() {
    if (!oculta() && devidaNaVolta) {
      devidaNaVolta = false;
      pedir();
    }
  }

  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
  }

  function parar() {
    clearTimeout(adiada);
    adiada = null;
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    }
  }

  return { pedir, parar };
}
