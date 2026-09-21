import { computed, ref, watch } from "vue";

import { fetchCommandItems, printCommandReceipt } from "../services/commandService";

/**
 * Tudo o que uma comanda tem e já teve, numa consulta só.
 *
 * Eram duas abas e duas consultas — "o que tem agora" e "histórico do cartão"
 * —, e quem abria o cartão via só a primeira. Só que a pergunta do operador é
 * a mesma nas duas: *o que passou por aqui?* Ele precisa do que está aberto
 * (é o que vai ser cobrado) E do que já foi, porque é assim que ele confere
 * uma reclamação de conta ou descobre que o item foi cancelado e não sumiu.
 *
 * O cuidado que as duas abas protegiam continua valendo e ficou mais visível:
 * o que está ABERTO nunca se mistura com o que já foi fechado. São dois grupos
 * rotulados, e o total que importa — o que vai para a conta — é só o do
 * primeiro. Um cartão reutilizado mostra o grupo aberto vazio e o histórico do
 * cliente anterior claramente marcado como passado.
 */
export function useCommandItems(commandRef) {
  const itens = ref([]);
  const carregando = ref(false);
  const imprimindo = ref(false);
  const erro = ref("");

  /** O que entra na próxima conta. É o único total que vira dinheiro. */
  const pendentes = computed(() =>
    itens.value.filter((item) => item.command_status === "pending"),
  );

  /** O que já foi cobrado ou cancelado — não entra em conta nenhuma. */
  const fechados = computed(() =>
    itens.value.filter((item) => item.command_status !== "pending"),
  );

  const total = computed(() => somar(pendentes.value));
  const totalHistorico = computed(() => somar(fechados.value));

  function somar(lista) {
    return lista.reduce((soma, item) => soma + Number(item.total_price || 0), 0);
  }

  function idAtual() {
    return commandRef.value?.id || null;
  }

  async function carregar() {
    const id = idAtual();
    if (!id) return;
    carregando.value = true;
    erro.value = "";
    try {
      // `history` traz TUDO, inclusive os pendentes — a separação é feita
      // aqui, e não por duas idas ao servidor.
      const dados = await fetchCommandItems(id, { history: true });
      itens.value = dados?.items || [];
    } catch (exc) {
      erro.value = exc?.response?.data?.detail || "Não foi possível ler a comanda.";
      itens.value = [];
    } finally {
      carregando.value = false;
    }
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

  watch(() => commandRef.value?.id, carregar, { immediate: true });

  return {
    itens,
    pendentes,
    fechados,
    carregando,
    imprimindo,
    erro,
    total,
    totalHistorico,
    carregar,
    imprimir,
  };
}
