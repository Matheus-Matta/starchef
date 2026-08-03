import { onBeforeUnmount, onMounted } from "vue";

const DEDUPE_WINDOW_MS = 4000;

/**
 * Escuta o evento `app:unhandled-error` despachado por `app.config.errorHandler`
 * (main.js) e dá ao usuário algum retorno visível — antes disso, um erro não
 * tratado em qualquer componente quebrava a tela em silêncio.
 *
 * Não usa o próprio errorHandler diretamente porque ele roda fora do contexto
 * de um componente Vue (sem acesso a `useToast()`); o evento em `window` é a
 * ponte entre os dois mundos.
 */
export function useGlobalErrorHandler(toast) {
  let lastMessage = "";
  let lastAt = 0;

  function handleUnhandledError(event) {
    const { error } = event.detail || {};
    const message = error?.message || String(error || "Erro desconhecido");
    const now = Date.now();
    if (message === lastMessage && now - lastAt < DEDUPE_WINDOW_MS) return;
    lastMessage = message;
    lastAt = now;

    toast.add({
      severity: "error",
      summary: "Algo deu errado",
      detail: "Ocorreu um erro inesperado. Se o problema persistir, recarregue a página.",
      life: 8000,
    });
  }

  onMounted(() => window.addEventListener("app:unhandled-error", handleUnhandledError));
  onBeforeUnmount(() => window.removeEventListener("app:unhandled-error", handleUnhandledError));
}
