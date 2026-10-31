import { formatMoney } from "../../utils/format";

export function cartoesDaVisaoGeral(vendas = {}, comandas = {}) {
  const plural = (n, um, varios) => `${n} ${Number(n) === 1 ? um : varios}`;
  const candidatos = [
    {
      grupo: "periodo", chave: "vendido", valor: vendas.vendido, rotulo: "Faturamento", tom: "success",
      icone: "dollar-sign", legenda: "Total recebido em pedidos", dinheiro: true, sempre: true,
    },
    {
      grupo: "periodo", chave: "pedidos", valor: vendas.pedidos, rotulo: "Pedidos", tom: "brand",
      icone: "receipt-text", legenda: "Todos os pedidos iniciados", sempre: true,
    },
    {
      grupo: "periodo", chave: "pedidos_pagos", valor: vendas.pedidos_pagos, rotulo: "Pedidos pagos",
      tom: "success", icone: "check-circle", legenda: "Pagamentos concluídos", sempre: true,
    },
    {
      grupo: "periodo", chave: "ticket", valor: vendas.ticket_medio, rotulo: "Ticket médio", tom: "info",
      icone: "trending-up", legenda: "Por pedido pago", dinheiro: true, sempre: true,
    },
    {
      grupo: "periodo", chave: "abertos", valor: vendas.pedidos_abertos, rotulo: "Pedidos em aberto", tom: "warning",
      icone: "receipt-text", legenda: "Aguardando pagamento",
    },
    {
      grupo: "agora", chave: "comandas_em_uso", valor: comandas.em_uso, rotulo: "Comandas em uso", tom: "warning",
      icone: "clipboard-list", sempre: true,
      legenda: `${formatMoney(comandas.em_uso_valor)} a receber agora`,
    },
    {
      grupo: "agora", chave: "comandas_pagas", valor: comandas.pagas, rotulo: "Comandas pagas", tom: "brand",
      icone: "check-circle", sempre: true, legenda: `${formatMoney(comandas.pagas_valor)} recebidos no período`,
    },
    {
      grupo: "agora", chave: "comandas_usadas", valor: comandas.usadas, rotulo: "Comandas usadas", tom: "info",
      icone: "ticket", sempre: true,
      legenda: plural(comandas.itens_lancados || 0, "item lançado", "itens lançados"),
    },
    {
      grupo: "agora", chave: "ticket_comanda", valor: comandas.ticket_medio, rotulo: "Ticket por comanda",
      tom: "info", icone: "trending-up", legenda: "Média das comandas pagas", dinheiro: true, sempre: true,
    },
    {
      grupo: "periodo", chave: "cancelados", valor: vendas.pedidos_cancelados, rotulo: "Pedidos cancelados", tom: "danger",
      icone: "x", legenda: "",
    },
    {
      grupo: "periodo", chave: "descontos", valor: vendas.descontos, rotulo: "Descontos dados", tom: "danger",
      icone: "percentage", legenda: "Nos pedidos pagos", dinheiro: true,
    },
    {
      grupo: "agora", chave: "perdas_comanda", valor: comandas.perdas_valor, rotulo: "Consumo perdido",
      tom: "danger", icone: "x", dinheiro: true,
      legenda: plural(comandas.itens_perdidos || 0, "item encerrado sem venda", "itens encerrados sem venda"),
    },
  ];
  return candidatos
    .filter((cartao) => cartao.sempre || Number(cartao.valor) > 0)
    .map((cartao) => ({
      ...cartao,
      valor: cartao.dinheiro ? formatMoney(cartao.valor) : String(Number(cartao.valor || 0)),
    }));
}
