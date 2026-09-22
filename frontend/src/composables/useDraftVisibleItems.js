import { computed } from "vue";

/**
 * O CARRINHO COMO O OPERADOR O VÊ: o que ele passou agora, mais o que as
 * comandas já tinham anotado.
 *
 * Os dois grupos aparecem juntos porque a conta é UMA — o cliente confere um
 * total, não duas listas. O que os distingue é o selo "Comanda N" na linha e
 * o fato de a anotação não ter o X: ela não pertence a este carrinho, é
 * consumo que já existe no cartão.
 *
 * As anotações vêm ANTES do que foi passado agora: o que já estava no cartão
 * é o contexto, e o que o operador acabou de passar é o que ele está
 * conferindo. Inverter faria a linha nova sumir no meio de uma conta grande.
 *
 * Fica separado de `useOrderDraft` porque é uma pergunta de APRESENTAÇÃO —
 * "o que mostrar na lista" —, e não de estado: o rascunho continua guardando
 * só os itens que ele próprio criou.
 */
export function useDraftVisibleItems(itens, comandas) {
  const itensDasComandas = computed(() =>
    comandas.value.flatMap((comanda) =>
      (comanda.items || []).map((item) => ({
        ...item,
        // Prefixado pelo cartão: dois cartões podem trazer a mesma anotação
        // de um produto idêntico, e o `key` do laço precisa distinguir.
        _id: `comanda-${comanda.id}-${item.id}`,
        command_number: comanda.number,
      })),
    ),
  );

  const itensVisiveis = computed(() => [...itensDasComandas.value, ...itens.value]);

  const quantidadeDeItens = computed(() =>
    itensVisiveis.value.reduce((soma, item) => soma + Number(item.quantity || 0), 0),
  );

  const total = computed(() =>
    itensVisiveis.value.reduce(
      (soma, item) => soma + Number(item.unit_price || 0) * Number(item.quantity || 0),
      0,
    ),
  );

  return { itensVisiveis, quantidadeDeItens, total };
}
