import { computed, ref } from "vue";

import {
  addCommand,
  cancelMerge,
  confirmMerge,
  fetchMerge,
  openMerge,
  printCommandReceipt,
  refundMerge,
  removeCommand,
} from "../services/orderMergeService";

/**
 * O estado da conta agrupada enquanto o caixa a monta.
 *
 * Duas decisões que o resto da tela depende:
 *
 * 1. **Conflito (409) não é erro de digitação.** O servidor responde 409
 *    quando outro caixa chegou antes ou quando o estado mudou embaixo da
 *    tela — "esta comanda já está em outra conta", "a comanda está em
 *    fechamento". A tela precisa distinguir isso de um 400 para não convidar
 *    o operador a tentar de novo o que nunca vai passar.
 * 2. **A chave de idempotência nasce ao abrir a conta, não ao clicar.** Um
 *    clique duplo em "Confirmar" reenvia a MESMA chave, e o servidor devolve
 *    a consolidação que já existe em vez de montar outra.
 */
export function useOrderMerge() {
  const merge = ref(null);
  const loading = ref(false);
  const error = ref("");
  const conflict = ref(false);
  const idempotencyKey = ref("");

  const sources = computed(() => merge.value?.sources || []);
  const items = computed(() => merge.value?.items || []);
  const total = computed(() => Number(merge.value?.total || 0));
  const subtotal = computed(() => Number(merge.value?.subtotal || 0));
  const serviceFee = computed(() => Number(merge.value?.service_fee || 0));
  const discount = computed(() => Number(merge.value?.discount || 0));
  const isOpen = computed(() => merge.value?.status === "open");
  const isConfirmed = computed(() => merge.value?.status === "confirmed");
  const isPaid = computed(() => merge.value?.status === "paid");
  const targetOrderId = computed(() => merge.value?.target_order || null);

  /** Os itens agrupados POR COMANDA — é como o cliente pergunta. */
  const itemsByCommand = computed(() => {
    const grupos = new Map();
    for (const item of items.value) {
      const chave = item.command || "sem-comanda";
      if (!grupos.has(chave)) {
        grupos.set(chave, {
          commandId: item.command,
          number: item.command_number,
          code: item.command_code,
          items: [],
          total: 0,
        });
      }
      const grupo = grupos.get(chave);
      grupo.items.push(item);
      grupo.total += Number(item.total_price || 0);
    }
    return [...grupos.values()].sort((a, b) => (a.number || 0) - (b.number || 0));
  });

  function novaChave() {
    // `crypto.randomUUID` não existe em contexto inseguro (http puro numa
    // loja sem TLS interno), e é exatamente onde o PDV web roda em parte das
    // instalações. O fallback mantém a chave única o suficiente.
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return `merge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  async function executar(acao) {
    loading.value = true;
    error.value = "";
    conflict.value = false;
    try {
      merge.value = await acao();
      return merge.value;
    } catch (exc) {
      const status = exc?.response?.status;
      conflict.value = status === 409;
      error.value =
        exc?.response?.data?.detail ||
        exc?.response?.data?.error?.message ||
        "Não foi possível concluir a operação.";
      return null;
    } finally {
      loading.value = false;
    }
  }

  async function start(orderId) {
    idempotencyKey.value = novaChave();
    return executar(() => openMerge(orderId));
  }

  async function load(mergeId) {
    if (!idempotencyKey.value) idempotencyKey.value = novaChave();
    return executar(() => fetchMerge(mergeId));
  }

  async function include(reference) {
    if (!merge.value || !String(reference || "").trim()) return null;
    return executar(() => addCommand(merge.value.id, String(reference).trim()));
  }

  async function exclude(commandId) {
    if (!merge.value) return null;
    return executar(() => removeCommand(merge.value.id, commandId));
  }

  async function confirm() {
    if (!merge.value) return null;
    return executar(() => confirmMerge(merge.value.id, idempotencyKey.value));
  }

  async function discard(reason = "") {
    if (!merge.value) return null;
    return executar(() => cancelMerge(merge.value.id, reason));
  }

  /** Estorna a venda já paga. Devolve o relatório do que foi desfeito. */
  async function refund(reason) {
    if (!merge.value) return null;
    const resultado = await executar(() => refundMerge(merge.value.id, reason));
    return resultado?.refund || null;
  }

  /** Imprime a conferência de uma das comandas da conta. */
  async function receipt(commandId) {
    error.value = "";
    try {
      return await printCommandReceipt(commandId);
    } catch (exc) {
      error.value = exc?.response?.data?.detail || "Não foi possível imprimir a conferência.";
      return null;
    }
  }

  function reset() {
    merge.value = null;
    error.value = "";
    conflict.value = false;
    idempotencyKey.value = "";
  }

  return {
    merge,
    loading,
    error,
    conflict,
    sources,
    items,
    itemsByCommand,
    subtotal,
    serviceFee,
    discount,
    total,
    isOpen,
    isConfirmed,
    isPaid,
    targetOrderId,
    start,
    load,
    include,
    exclude,
    confirm,
    discard,
    refund,
    receipt,
    reset,
  };
}
