import { computed, ref } from "vue";

import { materializeDraft } from "../services/orderDraftService";

/**
 * O carrinho ANTES de existir pedido — o padrão de PDV de mercado.
 *
 * Passar produtos não abre nada em lugar nenhum: os itens ficam na memória da
 * tela até alguém de fora precisar do pedido (a cozinha, para imprimir; o
 * caixa, para receber). É `materializeDraft` quem faz essa passagem.
 *
 * A comanda aqui é um ATRIBUTO do rascunho, não um gesto que cria pedido.
 * Escolher a comanda 13 e desistir não deixa o cartão ocupado — que era
 * exatamente o que acontecia quando a escolha disparava `open-command`.
 */
export function useOrderDraft() {
  const itens = ref([]);
  const comanda = ref(null);
  const mesa = ref(null);
  const cliente = ref(null);
  const tipo = ref("counter");
  const materializando = ref(false);

  let proximoId = 1;

  const vazio = computed(() => itens.value.length === 0);
  const quantidadeDeItens = computed(() =>
    itens.value.reduce((soma, item) => soma + Number(item.quantity || 0), 0),
  );
  const total = computed(() =>
    itens.value.reduce(
      (soma, item) => soma + Number(item.unit_price || 0) * Number(item.quantity || 0),
      0,
    ),
  );

  /**
   * Acrescenta um produto ao rascunho.
   *
   * Item igual (mesmo produto, mesma configuração, mesma observação) soma
   * quantidade em vez de virar uma segunda linha — é o que o operador espera
   * ao passar o mesmo refrigerante três vezes. Produto por peso nunca agrupa:
   * cada pesagem é uma medição própria.
   */
  function adicionar(produto, configuracao = {}) {
    const porPeso = produto.pricing_unit === "kg" || Boolean(configuracao.weight_kg);
    const novo = {
      _id: proximoId++,
      product: produto.id,
      product_name: produto.name,
      pricing_unit: produto.pricing_unit,
      unit_price: Number(configuracao.unit_price ?? produto.sale_price ?? 0),
      quantity: Number(configuracao.quantity ?? 1),
      variations: configuracao.variations || [],
      addons: configuracao.addons || [],
      customer_note: configuracao.customer_note || "",
      ...(configuracao.weight_kg ? { weight_kg: configuracao.weight_kg } : {}),
      ...(configuracao.scale_reading ? { scale_reading: configuracao.scale_reading } : {}),
    };

    if (!porPeso) {
      const igual = itens.value.find((item) => _mesmaConfiguracao(item, novo));
      if (igual) {
        igual.quantity = Number(igual.quantity) + Number(novo.quantity);
        return igual;
      }
    }
    itens.value.push(novo);
    return novo;
  }

  function mudarQuantidade(localId, quantidade) {
    const item = itens.value.find((linha) => linha._id === localId);
    if (!item) return;
    if (quantidade <= 0) {
      remover(localId);
      return;
    }
    item.quantity = quantidade;
  }

  /** No rascunho, remover é remover: nada foi para a cozinha, não há o que
   *  justificar. O cancelamento com motivo existe depois do pedido criado. */
  function remover(localId) {
    itens.value = itens.value.filter((linha) => linha._id !== localId);
  }

  function anexarComanda(escolhida, mesaDaComanda = null) {
    comanda.value = escolhida;
    mesa.value = mesaDaComanda;
    tipo.value = escolhida ? "command" : "counter";
  }

  function soltarComanda() {
    comanda.value = null;
    mesa.value = null;
    tipo.value = "counter";
  }

  function limpar() {
    itens.value = [];
    comanda.value = null;
    mesa.value = null;
    cliente.value = null;
    tipo.value = "counter";
  }

  /**
   * Cria o pedido de verdade e devolve o que o servidor gravou.
   *
   * O rascunho NÃO é limpo aqui: quem chamou decide, depois de a navegação
   * para o pedido dar certo. Limpar antes perderia o carrinho se a tela
   * seguinte falhasse ao carregar.
   */
  async function materializar(restaurantId) {
    materializando.value = true;
    try {
      return await materializeDraft({
        orderType: tipo.value,
        restaurantId,
        commandId: comanda.value?.id || null,
        tableId: mesa.value?.id || null,
        customerId: cliente.value?.id || null,
        items: itens.value,
      });
    } finally {
      materializando.value = false;
    }
  }

  return {
    itens,
    comanda,
    mesa,
    cliente,
    tipo,
    vazio,
    quantidadeDeItens,
    total,
    materializando,
    adicionar,
    mudarQuantidade,
    remover,
    anexarComanda,
    soltarComanda,
    limpar,
    materializar,
  };
}

function _mesmaConfiguracao(a, b) {
  return (
    a.product === b.product &&
    a.customer_note === b.customer_note &&
    JSON.stringify(a.variations) === JSON.stringify(b.variations) &&
    JSON.stringify(a.addons) === JSON.stringify(b.addons)
  );
}
