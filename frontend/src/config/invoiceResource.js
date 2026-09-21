import { EMISSION_TYPE_LABELS, INVOICE_STATUS_LABELS } from "./enums";

const labelOptions = (labels) => Object.entries(labels).map(([value, label]) => ({ value, label }));

export const invoiceProConfig = {
  defaultOrdering: "-created_at",
  filterFields: [
    { name: "status", label: "Status", options: labelOptions(INVOICE_STATUS_LABELS) },
    { name: "emission_type", label: "Emissão", options: labelOptions(EMISSION_TYPE_LABELS) },
  ],
  bulkActions: [
    {
      key: "resend-invoices",
      label: "Reenviar NFC-e",
      icon: "pi pi-send",
      type: "invoice-bulk-resend",
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
