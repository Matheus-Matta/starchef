import { onBeforeUnmount, onMounted } from "vue";

/**
 * Recarrega a tela a cada `intervalo` ms enquanto ela está aberta.
 *
 * `carregar` recebe `{ silencioso: true }` para não piscar a tela de
 * carregamento a cada volta. Uma volta lenta não empilha outra por cima, e a
 * aba escondida não consulta o servidor à toa.
 */
export function useAutoRefresh(carregar, intervalo = 30_000) {
  let timer = null;
  let ocupado = false;

  async function volta() {
    if (ocupado || document.hidden) return;
    ocupado = true;
    try {
      await carregar({ silencioso: true });
    } finally {
      ocupado = false;
    }
  }

  onMounted(() => {
    timer = window.setInterval(volta, intervalo);
  });
  onBeforeUnmount(() => window.clearInterval(timer));
}
