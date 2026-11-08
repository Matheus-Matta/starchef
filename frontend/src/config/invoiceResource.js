import { API_BASE_URL } from "../services/api";
import { EMISSION_TYPE_LABELS, INVOICE_PHASE_LABELS, INVOICE_STATUS_LABELS } from "./enums";

const labelOptions = (labels) => Object.entries(labels).map(([value, label]) => ({ value, label }));

/** Nota que não saiu: com erro, ou em contingência esperando transmissão. */
const travada = (row) => row.status === "error" || (row.status === "pending" && row.emission_type === "9");

const RECREATE_MESSAGE =
  "A tentativa travada (XML, chave e contingência) é descartada e a nota é emitida de novo, " +
  "com a data de hoje e o mesmo número. Use quando o reenvio não resolve — por exemplo, " +
  "depois das 24 h da contingência. Um cupom de contingência já impresso deixa de valer.";

export const invoiceProConfig = {
  defaultOrdering: "-created_at",
  filterFields: [
    { name: "status", label: "Status", compact: true, options: labelOptions(INVOICE_STATUS_LABELS) },
    { name: "emission_type", label: "Emissão", compact: true, options: labelOptions(EMISSION_TYPE_LABELS) },
  ],
  headerActions: [
    { key: "export-xml", label: "Exportar XML", icon: "pi pi-file-export", type: "route", routeName: "notas-fiscais-exportar-xml" },
  ],
  bulkActions: [
    {
      key: "resend-invoices",
      label: "Reenviar NFC-e",
      icon: "pi pi-send",
      type: "invoice-bulk-resend",
      endpoint: "/invoices/bulk-resend/",
      confirmHeader: "Confirmar reenvio em massa",
      confirmMessage: "Reenviar as notas selecionadas?",
      acceptLabel: "Reenviar",
      errorSummary: "Não foi possível reenviar as notas",
    },
    {
      key: "recreate-invoices",
      label: "Recriar NFC-e",
      icon: "pi pi-refresh",
      type: "invoice-bulk-recreate",
      endpoint: "/invoices/bulk-recreate/",
      confirmHeader: "Confirmar recriação em massa",
      confirmMessage: `Recriar as notas selecionadas? ${RECREATE_MESSAGE}`,
      acceptLabel: "Recriar",
      errorSummary: "Não foi possível recriar as notas",
    },
    {
      // A nota é do pedido: cancelar o pedido cancela a nota junto (e os
      // pagamentos e o caixa). Cancelar só a nota deixaria uma venda viva sem
      // documento fiscal — por isso a ação daqui é a mesma da lista de pedidos.
      key: "cancel-orders",
      label: "Cancelar pedidos e notas",
      icon: "pi pi-times-circle",
      type: "order-bulk-cancel",
      idField: "order",
    },
  ],
  rowActions: [
    {
      key: "resend",
      label: "Reenviar nota",
      icon: "pi pi-send",
      type: "post-detail",
      action: "resend",
      confirmMessage: "Reenviar somente esta nota?",
      confirmAcceptLabel: "Reenviar",
      successSummary: (data) => (data.status === "issued" ? "Nota autorizada" : "Nota reenviada"),
      successDetail: (data) => (data.status === "issued" ? "A SEFAZ autorizou a nota." : "A nota continua em processamento."),
      successSeverity: (data) => (data.status === "issued" ? "success" : "info"),
      errorSummary: "Não foi possível reenviar a nota",
      visible: travada,
    },
    {
      key: "recreate",
      label: "Recriar nota",
      icon: "pi pi-refresh",
      type: "post-detail",
      action: "recreate",
      confirmMessage: `Recriar esta nota? ${RECREATE_MESSAGE}`,
      confirmAcceptLabel: "Recriar",
      successSummary: (data) => (data.status === "issued" ? "Nota recriada e autorizada" : "Nota recriada"),
      successDetail: (data) => (data.status === "issued"
        ? "A SEFAZ autorizou a nova emissão."
        : data.error_message || "A nova emissão está em andamento."),
      successSeverity: (data) => ({ issued: "success", error: "warn" })[data.status] || "info",
      errorSummary: "Não foi possível recriar a nota",
      visible: travada,
    },
    {
      // Link direto: o cookie de sessão vai junto e o servidor responde como
      // anexo, então o navegador baixa o arquivo sem trocar de página.
      key: "xml",
      label: "Baixar XML",
      icon: "pi pi-download",
      type: "external",
      href: (row) => `${API_BASE_URL}/invoices/${row.id}/xml/`,
      visible: (row) => Boolean(row.xml_content),
    },
  ],
};

export const invoiceColumns = [
  { key: "number", label: "Numero" },
  { key: "order_sequence", label: "Pedido", type: "order-link", idKey: "order", showInList: false },
  { key: "phase", label: "Tipo", map: INVOICE_PHASE_LABELS },
  { key: "status", label: "Status", type: "status", map: INVOICE_STATUS_LABELS },
  { key: "emission_type", label: "Emissão", type: "status", map: EMISSION_TYPE_LABELS },
  { key: "total_amount", label: "Valor", type: "money", align: "right" },
  { key: "issued_at", label: "Emissão em", type: "date" },
  { key: "error_message", label: "Motivo / erro", showInList: false },
];
