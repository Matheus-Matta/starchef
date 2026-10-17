import { ref } from "vue";

import { api } from "../services/api";

// Nota transmitida que só espera a resposta da SEFAZ: vale perguntar.
// Recusa, erro de configuração ou nota só na fila não têm o que imprimir.
const EM_CAMINHO = ["processing", "awaiting_transmission"];
const RECUSADA = ["rejected", "configuration_error"];
// Mesma espera crescente do PDV desktop (`home_page_fiscal.dart`).
const ESPERAS_MS = [1200, 2000, 3000, 4000, 5000];

const esperar = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const abrirJanela = () => window.open("", "_blank", "width=420,height=720");

/**
 * "Imprimir a NFC-e?" depois da venda, para o restaurante com `ask_print_danfe`.
 *
 * A nota é emitida pelo servidor de qualquer jeito; a pergunta decide só o
 * papel. Quem responde "Imprimir" antes de a SEFAZ autorizar não precisa
 * esperar com o modal aberto: a janela de impressão fica aguardando e o DANFE
 * entra nela quando a autorização chegar.
 */
export function useDanfePrintQuestion({ toast, sleep = esperar, openWindow = abrirJanela } = {}) {
  const pergunta = ref(null);

  async function oferecer(order, restaurant) {
    pergunta.value = null;
    if (!order?.id || !restaurant?.ask_print_danfe) return;
    let fiscal;
    let sequence = order.sequence;
    try {
      const { data } = await api.get(`/orders/${order.id}/`);
      fiscal = data.fiscal;
      sequence = data.sequence ?? sequence;
    } catch {
      return; // sem saber da nota não há o que perguntar; o pedido segue pago
    }
    if (!fiscal?.id || !(fiscal.printable || EM_CAMINHO.includes(fiscal.fiscal_state))) return;
    pergunta.value = {
      invoiceId: fiscal.id,
      printable: Boolean(fiscal.printable),
      summary: `Pedido #${sequence} · NFC-e ${fiscal.number ?? ""}`.trim(),
    };
  }

  function cancelar() {
    pergunta.value = null;
  }

  async function esperarAutorizacao(invoiceId) {
    for (const ms of ESPERAS_MS) {
      await sleep(ms);
      try {
        // `manual_print`: quem imprime é esta tela. Sem isso o cupom criado
        // pela consulta iria para o agente local e sairiam dois DANFEs.
        const { data } = await api.post(`/invoices/${invoiceId}/refresh-status/`, { manual_print: true });
        if (data.printable) return true;
        if (RECUSADA.includes(data.fiscal_state)) return false;
      } catch {
        // Tropeço de rede não abandona a nota: a próxima volta tenta de novo.
      }
    }
    return false;
  }

  // A janela abre AQUI, no gesto (Enter ou clique): aberta depois de um
  // `await`, o navegador a trata como pop-up e bloqueia.
  async function imprimir() {
    const alvo = pergunta.value;
    pergunta.value = null;
    if (!alvo) return;
    const win = openWindow();
    if (!win) {
      toast?.add({ severity: "warn", summary: "Pop-up bloqueado", detail: "Libere pop-ups para imprimir o DANFE.", life: 4000 });
      return;
    }
    win.document.write("<p style='font-family:sans-serif;padding:24px'>Aguardando autorização da SEFAZ...</p>");
    try {
      if (!alvo.printable && !(await esperarAutorizacao(alvo.invoiceId))) {
        win.close();
        toast?.add({
          severity: "warn",
          summary: "NFC-e ainda não autorizada",
          detail: "Quando a SEFAZ autorizar, imprima o DANFE pelo pedido em Pedidos.",
          life: 6000,
        });
        return;
      }
      const { data: job } = await api.post(`/invoices/${alvo.invoiceId}/print/`, {});
      win.document.open();
      win.document.write(job.html || "<p>DANFE indisponível.</p>");
      win.document.close();
      win.focus();
      win.print();
    } catch {
      win.close();
      toast?.add({ severity: "error", summary: "O DANFE não pôde ser gerado", detail: "Tente pelo pedido em Pedidos.", life: 5000 });
    }
  }

  return { pergunta, oferecer, imprimir, cancelar };
}
