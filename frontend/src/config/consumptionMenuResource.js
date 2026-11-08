// Cardápio de consumo: o que sai do estoque sozinho, no dia certo. A lista é
// genérica; o cadastro (cabeçalho + itens + previsão) tem tela própria.
export const CONSUMPTION_FREQUENCY_LABELS = { daily: "Todo dia", weekly: "Toda semana", monthly: "Todo mês" };

export const consumptionMenuResource = {
  name: "cardapios-consumo",
  documentView: true,
  module: "logistica",
  title: "Cardápios de consumo",
  endpoint: "/stock/consumption-menus/",
  pro: {
    primaryAction: { label: "Novo cardápio", icon: "pi pi-plus", route: "cardapio-consumo-novo" },
    detailRoute: "cardapio-consumo-documento",
  },
  columns: [
    { key: "nome", label: "Cardápio" },
    { key: "quando", label: "Quando sai" },
    { key: "local_nome", label: "Local" },
    { key: "confirma_sozinho", label: "Confirma sozinho", type: "boolean" },
    { key: "ativo", label: "Ativo", type: "boolean" },
  ],
};
