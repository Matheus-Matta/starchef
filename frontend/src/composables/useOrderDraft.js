import { computed, ref } from "vue";

import { useDraftVisibleItems } from "./useDraftVisibleItems";

import { materializeDraft } from "../services/orderDraftService";

/**
 * O carrinho ANTES de existir pedido — o padrão de PDV de mercado.
 *
 * Passar produtos não abre nada em lugar nenhum: os itens ficam na memória da
 * tela até alguém de fora precisar do pedido (a cozinha, para imprimir; o
 * caixa, para receber). É `materializeDraft` quem faz essa passagem.
 *
 * As comandas aqui são ATRIBUTOS do rascunho, não um gesto que cria pedido.
 * São VÁRIAS porque a mesa que paga junto é o caso, não a exceção — e o pedido
 * do caixa puxa as anotações pendentes de todas elas.
 *
 * Escolher a comanda 13 e desistir não deixa o cartão ocupado — que era
 * exatamente o que acontecia quando a escolha disparava `open-command`.
 */
export function useOrderDraft() {
  const itens = ref([]);
  const comandas = ref([]);
  const mesa = ref(null);
  const cliente = ref(null);
  const tipo = ref("counter");
  const materializando = ref(false);

  let proximoId = 1;

  // A lista que a tela mostra é pergunta de APRESENTAÇÃO, não de estado: o
  // rascunho guarda só os itens que ele próprio criou.
  const { itensVisiveis, quantidadeDeItens, total } = useDraftVisibleItems(
    itens,
    comandas,
  );

  const vazio = computed(() => itensVisiveis.value.length === 0);

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

  /**
   * Anexa um cartão. Passar o MESMO de novo não duplica.
   *
   * A mesa vem do PRIMEIRO cartão: ela diz onde a conta está sentada, e quatro
   * cartões da mesma mesa apontam para a mesma. O leitor dispara duas leituras
   * com frequência, e virar duas linhas do mesmo cartão cobraria em dobro.
   */
  function anexarComanda(escolhida, mesaDaComanda = null) {
    if (!escolhida?.id) return;
    if (!comandas.value.some((atual) => atual.id === escolhida.id)) {
      comandas.value = [...comandas.value, escolhida];
    }
    if (!mesa.value) mesa.value = mesaDaComanda;
    tipo.value = "command";
  }

  /**
   * Guarda as anotações que o cartão já tinha, para o carrinho mostrá-las.
   *
   * É só PRÉVIA: quem monta a conta de verdade é o `attach-commands` no
   * servidor, que relê as anotações pendentes no momento da abertura. Se
   * outro garçom lançar uma sobremesa entre anexar e cobrar, o servidor a
   * inclui — e é assim que tem de ser.
   */
  function registrarItensDaComanda(commandId, itensDoCartao) {
    comandas.value = comandas.value.map((atual) =>
      atual.id === commandId ? { ...atual, items: itensDoCartao } : atual,
    );
  }

  /** Solta UM cartão, ou todos quando não se diz qual. */
  function soltarComanda(commandId = null) {
    comandas.value = commandId
      ? comandas.value.filter((atual) => atual.id !== commandId)
      : [];
    if (!comandas.value.length) {
      mesa.value = null;
      tipo.value = "counter";
    }
  }

  function limpar() {
    itens.value = [];
    comandas.value = [];
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
        commandIds: comandas.value.map((atual) => atual.id),
        customerId: cliente.value?.id || null,
        items: itens.value,
      });
    } finally {
      materializando.value = false;
    }
  }

  return {
    itens,
    itensVisiveis,
    comandas,
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
    registrarItensDaComanda,
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
