import { EMISSION_TYPE_LABELS, INVOICE_STATUS_LABELS } from "./enums";

const labelOptions = (labels) => Object.entries(labels).map(([value, label]) => ({ value, label }));

export const invoiceProConfig = {
  defaultOrdering: "-created_at",
  filterFields: [
    { name: "status", label: "Status", compact: true, options: labelOptions(INVOICE_STATUS_LABELS) },
    { name: "emission_type", label: "Emissão", compact: true, options: labelOptions(EMISSION_TYPE_LABELS) },
  ],
  bulkActions: [
    {
      key: "resend-invoices",
      label: "Reenviar NFC-e",
      icon: "pi pi-send",
      type: "invoice-bulk-resend",
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
};

export const invoiceColumns = [
  { key: "number", label: "Numero" },
  { key: "order_sequence", label: "Pedido", type: "order-link", idKey: "order", showInList: false },
  { key: "phase", label: "Tipo" },
  { key: "status", label: "Status", type: "status", map: INVOICE_STATUS_LABELS },
  { key: "emission_type", label: "Emissão", type: "status", map: EMISSION_TYPE_LABELS },
  { key: "total_amount", label: "Valor", type: "money", align: "right" },
  { key: "issued_at", label: "Emissão em", type: "date" },
  { key: "error_message", label: "Motivo / erro", showInList: false },
];
