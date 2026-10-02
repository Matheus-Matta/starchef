/**
 * Eventos da linha do tempo da comanda (`GET /commands/{id}/history/`) em
 * linhas de tabela. O servidor manda o fato; aqui só se decide como lê-lo.
 */
const dinheiro = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const quando = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

function quantidade(valor) {
  const numero = Number(valor);
  if (!Number.isFinite(numero)) return "";
  return Number.isInteger(numero) ? String(numero) : numero.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}

export function linhaDoHistorico(evento) {
  const item = evento.item
    ? `${quantidade(evento.item.quantity)}× ${evento.item.product} · ${dinheiro.format(Number(evento.item.total || 0))}`
    : "";
  // O código do operador aparece junto do nome: num aparelho compartilhado
  // (totem, celular do salão) o usuário logado não diz quem lançou.
  const quem = [evento.user, evento.operator_code && `código ${evento.operator_code}`].filter(Boolean).join(" · ");
  return {
    key: `${evento.at}-${evento.kind}-${evento.item?.id || ""}`,
    quando: quando.format(new Date(evento.at)),
    acao: evento.label,
    tipo: evento.kind,
    item,
    quem: quem || "—",
    conta: evento.order ? `#${evento.order.sequence}` : "",
    mesa: evento.table ? `Mesa ${evento.table}` : "",
    motivo: evento.reason || "",
  };
}

export const colunasDoHistorico = [
  { key: "quando", label: "Quando" },
  { key: "acao", label: "Ação" },
  { key: "item", label: "Item" },
  { key: "quem", label: "Quem" },
  { key: "conta", label: "Conta" },
  { key: "mesa", label: "Mesa" },
  { key: "motivo", label: "Motivo" },
];
