import { computed, nextTick, ref } from "vue";

import { api } from "../services/api";
import { cnpjDigits, formatCnpj, isValidCnpj } from "../utils/cnpj";
import { cpfDigits, formatCpf, isValidCpf } from "../utils/cpf";

/**
 * As escolhas da tela de pagamento — taxa, desconto, CPF ou CNPJ — gravadas no
 * PEDIDO, e não na tela.
 *
 * Antes elas só iam para o servidor no "Fechar conta" (`/close/`), que ainda
 * mudava o pedido para "aguardando pagamento". Voltar à venda, trocar de
 * pedido ou recarregar a página perdia o que o operador marcou. Agora cada
 * escolha vai pelo `/checkout/`, que grava e recalcula sem avançar o pedido —
 * quem avança é o primeiro recebimento.
 *
 * CNPJ só aparece quando o servidor já o conhece (o pedido vem com
 * `fiscal_customer_cnpj`): antes disso, um CNPJ digitado seria ignorado e a
 * nota sairia sem documento sem ninguém perceber.
 */
export function useCheckoutChoices(estado, { onErro } = {}) {
  const { currentOrder, discount, discountInput, serviceFeeEnabled, includeCpfOnInvoice, invoiceCpf, invoiceCpfError } = estado;
  const includeCnpjOnInvoice = ref(false);
  const invoiceCnpj = ref("");
  const invoiceCnpjError = ref("");
  const cnpjDisponivel = computed(() => Boolean(currentOrder.value) && "fiscal_customer_cnpj" in currentOrder.value);
  let restaurando = false;

  /** Traz as escolhas gravadas no pedido para a tela. */
  function restaurar(order) {
    restaurando = true;
    discount.value = Number(order?.discount || 0);
    discountInput.value = discount.value.toFixed(2);
    serviceFeeEnabled.value = order?.service_fee_enabled !== false;
    invoiceCpf.value = formatCpf(order?.fiscal_customer_cpf || "");
    includeCpfOnInvoice.value = Boolean(invoiceCpf.value);
    invoiceCnpj.value = formatCnpj(order?.fiscal_customer_cnpj || "");
    includeCnpjOnInvoice.value = Boolean(invoiceCnpj.value) && !includeCpfOnInvoice.value;
    invoiceCpfError.value = "";
    invoiceCnpjError.value = "";
    nextTick(() => (restaurando = false));
  }

  /** CPF e CNPJ são um OU outro: marcar um desmarca o outro. */
  function alternarDocumento(qual) {
    if (qual === "cpf" && includeCpfOnInvoice.value) includeCnpjOnInvoice.value = false;
    if (qual === "cnpj" && includeCnpjOnInvoice.value) includeCpfOnInvoice.value = false;
  }

  /** O documento da nota pronto para enviar, ou o erro a mostrar. */
  function documento() {
    invoiceCpfError.value = "";
    invoiceCnpjError.value = "";
    const corpo = { fiscal_customer_cpf: "" };
    if (cnpjDisponivel.value) corpo.fiscal_customer_cnpj = "";
    if (includeCpfOnInvoice.value) {
      if (!isValidCpf(invoiceCpf.value)) return { erro: (invoiceCpfError.value = "Informe um CPF válido.") };
      corpo.fiscal_customer_cpf = cpfDigits(invoiceCpf.value);
    } else if (includeCnpjOnInvoice.value && cnpjDisponivel.value) {
      if (!isValidCnpj(invoiceCnpj.value)) return { erro: (invoiceCnpjError.value = "Informe um CNPJ válido.") };
      corpo.fiscal_customer_cnpj = cnpjDigits(invoiceCnpj.value);
    }
    return { corpo };
  }

  function corpo(extra = {}) {
    const { corpo: doc } = documento();
    return { discount: discount.value || 0, service_fee_enabled: serviceFeeEnabled.value, ...doc, ...extra };
  }

  /**
   * Grava as escolhas no pedido. Sem pedido, durante a restauração ou com
   * documento ainda incompleto, não chama o servidor: o operador está no meio
   * da digitação, e o erro aparece no campo quando ele for pagar.
   */
  async function salvar() {
    if (restaurando || !currentOrder.value?.id) return;
    if (documento().erro) return;
    try {
      const { data } = await api.post(`/orders/${currentOrder.value.id}/checkout/`, corpo());
      currentOrder.value = data;
    } catch (erro) {
      onErro?.(erro);
    }
  }

  return {
    includeCnpjOnInvoice,
    invoiceCnpj,
    invoiceCnpjError,
    cnpjDisponivel,
    restaurar,
    alternarDocumento,
    documento,
    corpo,
    salvar,
  };
}
