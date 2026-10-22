import { formatMoney } from "../../utils/format";

/**
 * Os números do topo da Visão Geral. O servidor já tira o que é zero; aqui
 * um cartão só aparece se o número dele chegou — nada de "R$ 0,00" ocupando
 * espaço numa manhã sem cancelamento.
 */
export function cartoesDaVisaoGeral(vendas = {}, comandas = {}) {
  const plural = (n, um, varios) => `${n} ${Number(n) === 1 ? um : varios}`;
  const candidatos = [
    {
      chave: "vendido", valor: vendas.vendido, rotulo: "Vendas", tom: "success", icone: "dollar-sign",
      legenda: vendas.pedidos_pagos ? plural(vendas.pedidos_pagos, "pedido pago", "pedidos pagos") : "",
      dinheiro: true,
    },
    {
      chave: "ticket", valor: vendas.ticket_medio, rotulo: "Ticket médio", tom: "info", icone: "trending-up",
      legenda: "Por pedido pago", dinheiro: true,
    },
    {
      chave: "abertos", valor: vendas.pedidos_abertos, rotulo: "Pedidos em aberto", tom: "warning",
      icone: "receipt-text", legenda: "Aguardando pagamento",
    },
    {
      chave: "comandas_abertas", valor: comandas.abertas, rotulo: "Comandas em aberto", tom: "warning",
      icone: "clipboard-list",
      legenda: comandas.abertas_valor ? `${formatMoney(comandas.abertas_valor)} a receber` : "",
    },
    {
      chave: "comandas_pagas", valor: comandas.pagas, rotulo: "Comandas pagas", tom: "brand", icone: "check-circle",
      legenda: comandas.pagas_valor ? `${formatMoney(comandas.pagas_valor)} recebidos` : "",
    },
    {
      chave: "ticket_comanda", valor: comandas.ticket_medio, rotulo: "Ticket por comanda", tom: "info",
      icone: "trending-up", legenda: "Média das comandas pagas", dinheiro: true,
    },
    {
      chave: "cancelados", valor: vendas.pedidos_cancelados, rotulo: "Pedidos cancelados", tom: "danger",
      icone: "x", legenda: "",
    },
    {
      chave: "descontos", valor: vendas.descontos, rotulo: "Descontos dados", tom: "danger", icone: "percentage",
      legenda: "Nos pedidos pagos", dinheiro: true,
    },
  ];
  return candidatos
    .filter((cartao) => Number(cartao.valor) > 0)
    .map((cartao) => ({ ...cartao, valor: cartao.dinheiro ? formatMoney(cartao.valor) : String(cartao.valor) }));
}
