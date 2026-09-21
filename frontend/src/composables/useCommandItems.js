import { computed, ref, watch } from "vue";

import { fetchCommandItems, printCommandReceipt } from "../services/commandService";

/**
 * O que uma comanda tem, e o que ela já teve.
 *
 * A lógica sai do componente porque ela responde a uma pergunta de DOMÍNIO, e
 * a pergunta é sutil: `command.items` no backend devolve o histórico inteiro
 * do cartão. "O que tem agora" e "o que este cartão já consumiu" são duas
 * consultas diferentes, e misturá-las faz a comanda reutilizada reaparecer
 * cheia com a conta do cliente anterior.
 *
 * `emFechamento` vem de `closing_merge` na resposta — derivado, nunca um
 * estado gravado na comanda.
 */
export function useCommandItems(commandRef) {
  const itens = ref([]);
  const carregando = ref(false);
  const imprimindo = ref(false);
  const historico = ref(false);
  const erro = ref("");
  const emFechamento = ref(false);

  const total = computed(() =>
    itens.value.reduce((soma, item) => soma + Number(item.total_price || 0), 0),
  );

  function idAtual() {
    return commandRef.value?.id || null;
  }

  async function carregar() {
    const id = idAtual();
    if (!id) return;
    carregando.value = true;
    erro.value = "";
    try {
      const dados = await fetchCommandItems(id, { history: historico.value });
      itens.value = dados?.items || [];
      emFechamento.value = Boolean(dados?.closing_merge);
    } catch (exc) {
      erro.value = exc?.response?.data?.detail || "Não foi possível ler a comanda.";
      itens.value = [];
    } finally {
      carregando.value = false;
    }
  }

  /** Trocar de aba é uma consulta nova, não um filtro sobre o que já veio. */
  function trocarAba(valor) {
    if (historico.value === valor) return;
    historico.value = valor;
    carregar();
  }

  /**
   * Imprime a conferência. Devolve `true` quando o papel foi para a fila.
   *
   * Não é documento fiscal: a NFC-e é uma só, do pedido consolidado.
   */
  async function imprimir() {
    const id = idAtual();
    if (!id) return false;
    imprimindo.value = true;
    erro.value = "";
    try {
      await printCommandReceipt(id);
      return true;
    } catch (exc) {
      erro.value = exc?.response?.data?.detail || "Não foi possível imprimir a conferência.";
      return false;
    } finally {
      imprimindo.value = false;
    }
  }

  // Trocar de comanda volta para "o que tem agora": o histórico é uma consulta
  // que o operador pediu para AQUELE cartão, não um modo da tela.
  watch(
    () => commandRef.value?.id,
    () => {
      historico.value = false;
      carregar();
    },
    { immediate: true },
  );

  return {
    itens,
    carregando,
    imprimindo,
    historico,
    erro,
    emFechamento,
    total,
    carregar,
    trocarAba,
    imprimir,
  };
}
