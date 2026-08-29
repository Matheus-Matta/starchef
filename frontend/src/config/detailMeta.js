/**
 * Configuracao visual da tela de detalhe (modo "ver") por tipo de recurso.
 * Define o cabecalho colorido (hero), as metricas em destaque e o badge de status.
 * Substitui a logica que antes vivia dentro do antigo drawer.
 *
 * Cada meta pode ter:
 *  - icon / accent / eyebrow : aparencia do hero
 *  - title(row) / subtitle(row) : textos do hero
 *  - badge(row) : rotulo do selo de status (opcional)
 *  - badgeKey : chave da coluna que o badge representa (excluida do grid de campos)
 *  - metrics : [{ label, key, type?, suffix? }] cartoes de metrica no topo
 */
import {
  CASH_STATUS_LABELS,
  ORDER_STATUS_LABELS,
  ORDER_TYPE_LABELS,
  PROFILE_TYPE_LABELS,
  TABLE_STATUS_LABELS,
} from "./enums";
import { formatMoney } from "../utils/format";

/** Descobre o "tipo de detalhe" a partir do endpoint da API. */
export function resolveDetailType(endpoint) {
  const rules = [
    ["/menu/products", "product"],
    ["/orders", "order"],
    ["/tables", "table"],
    ["/customers", "customer"],
    ["/cash-register", "cash"],
    ["/menu/categories", "category"],
    ["/menu/ingredients", "ingredient"],
    ["/menu/recipes", "recipe"],
    ["/menu/menus", "menu"],
    ["/menu/addons", "addon"],
    ["/stock/movements", "stock"],
    ["/stock/locations", "location"],
    ["/delivery/zones", "zone"],
    ["/delivery/deliverymen", "deliveryman"],
    ["/payments/methods", "paymentMethod"],
    ["/payments", "payment"],
    ["/fiscal/profiles", "fiscalProfile"],
    ["/invoices", "invoice"],
    ["/printers", "printer"],
    ["/scales", "scale"],
    ["/restaurants", "restaurant"],
    ["/branches", "branch"],
    ["/users", "user"],
    ["/roles", "role"],
    ["/kitchen/stations", "station"],
  ];
  return rules.find(([path]) => endpoint.includes(path))?.[1] ?? "generic";
}

export const DETAIL_META = {
  product: {
    icon: "pi-shopping-bag", accent: "violet", eyebrow: "Produto",
    title: (r) => r.name || "Produto",
    subtitle: (r) => r.category_name || "Sem categoria",
    metrics: [
      { label: "Preco", key: "current_price", type: "money" },
      { label: "Preparo", key: "average_preparation_time", suffix: " min" },
      { label: "Margem", key: "margin_percent", type: "percent" },
      { label: "Custo", key: "estimated_cost", type: "money" },
    ],
  },
  order: {
    icon: "pi-receipt", accent: "violet", eyebrow: "Pedido", badgeKey: "status",
    title: (r) => `Pedido #${r.sequence ?? "-"}`,
    subtitle: (r) => ORDER_TYPE_LABELS[r.order_type] || "Pedido",
    badge: (r) => ORDER_STATUS_LABELS[r.status] || r.status,
    metrics: [
      { label: "Total", key: "total", type: "money" },
      { label: "Comanda", key: "command_number" },
      { label: "Mesa", key: "table_number" },
      { label: "Cliente", key: "customer_name" },
    ],
  },
  table: {
    icon: "pi-table", accent: "blue", eyebrow: "Mesa", badgeKey: "status",
    title: (r) => `Mesa ${r.number || "-"}`,
    subtitle: (r) => r.sector_name || "Sem setor",
    badge: (r) => TABLE_STATUS_LABELS[r.status] || r.status,
    metrics: [{ label: "Capacidade", key: "capacity", suffix: " lugares" }],
  },
  customer: {
    icon: "pi-user", accent: "teal", eyebrow: "Cliente",
    title: (r) => r.name || "Cliente",
    subtitle: (r) => r.phone || r.email || "Sem contato",
  },
  cash: {
    icon: "pi-wallet", accent: "green", eyebrow: "Caixa", badgeKey: "status",
    title: () => "Caixa",
    subtitle: (r) => CASH_STATUS_LABELS[r.status] || r.status,
    badge: (r) => CASH_STATUS_LABELS[r.status] || r.status,
    metrics: [
      { label: "Abertura", key: "opening_amount", type: "money" },
      { label: "Esperado", key: "expected_amount", type: "money" },
    ],
  },
  user: {
    icon: "pi-user", accent: "indigo", eyebrow: "Usuario", badgeKey: "profile.profile_type",
    title: (r) => r.first_name || r.username || "Usuario",
    subtitle: (r) => r.email || r.username,
    badge: (r) => PROFILE_TYPE_LABELS[r.profile?.profile_type] || r.profile?.profile_type || "-",
  },
  payment: {
    icon: "pi-dollar", accent: "teal", eyebrow: "Pagamento",
    title: (r) => formatMoney(r.amount),
    subtitle: (r) => r.payment_method?.name || "Pagamento",
    metrics: [
      { label: "Valor", key: "amount", type: "money" },
      { label: "Troco", key: "change_amount", type: "money" },
    ],
  },
  ingredient: {
    icon: "pi-box", accent: "amber", eyebrow: "Ingrediente",
    title: (r) => r.name || "Ingrediente",
    subtitle: (r) => `Unidade: ${r.unit || "-"}`,
    metrics: [
      { label: "Custo medio", key: "average_cost", type: "money" },
      { label: "Estoque min.", key: "minimum_stock" },
    ],
  },
  station: {
    icon: "pi-desktop", accent: "green", eyebrow: "Estacao KDS",
    title: (r) => r.name || "Estacao",
    subtitle: (r) => r.restaurant_name || "-",
    metrics: [{ label: "SLA", key: "sla_minutes", suffix: " min" }],
  },
  branch: { icon: "pi-sitemap", accent: "blue", eyebrow: "Filial", title: (r) => r.name || "Filial", subtitle: (r) => r.restaurant_name || "-" },
  restaurant: { icon: "pi-building", accent: "violet", eyebrow: "Restaurante", title: (r) => r.trade_name || "Restaurante", subtitle: (r) => r.city || r.legal_name || "-" },
  category: { icon: "pi-tags", accent: "indigo", eyebrow: "Categoria", title: (r) => r.name || "Categoria" },
  recipe: { icon: "pi-book", accent: "amber", eyebrow: "Receita", title: (r) => r.product?.name || "Receita" },
  menu: { icon: "pi-bookmark", accent: "indigo", eyebrow: "Cardapio", title: (r) => r.name || "Cardapio" },
  addon: { icon: "pi-plus-circle", accent: "teal", eyebrow: "Adicional", title: (r) => r.name || "Adicional" },
  stock: { icon: "pi-database", accent: "amber", eyebrow: "Movimentacao", title: (r) => r.ingredient_name || "Movimentacao" },
  location: { icon: "pi-map-marker", accent: "slate", eyebrow: "Local de estoque", title: (r) => r.name || "Local" },
  zone: { icon: "pi-map", accent: "blue", eyebrow: "Zona de entrega", title: (r) => r.name || "Zona" },
  deliveryman: { icon: "pi-truck", accent: "green", eyebrow: "Entregador", title: (r) => r.name || "Entregador" },
  paymentMethod: { icon: "pi-credit-card", accent: "teal", eyebrow: "Forma de pagamento", title: (r) => r.name || "Forma" },
  invoice: { icon: "pi-file", accent: "indigo", eyebrow: "Nota fiscal", title: (r) => r.number || "Nota" },
  fiscalProfile: {
    icon: "pi-percentage", accent: "amber", eyebrow: "Perfil fiscal",
    title: (r) => r.name || "Perfil fiscal",
    subtitle: (r) => [r.ncm && `NCM ${r.ncm}`, r.cfop && `CFOP ${r.cfop}`].filter(Boolean).join(" · ") || "-",
  },
  printer: { icon: "pi-print", accent: "slate", eyebrow: "Impressora", title: (r) => r.name || "Impressora" },
  scale: { icon: "pi-gauge", accent: "green", eyebrow: "Balanca", title: (r) => r.name || "Balanca" },
  role: { icon: "pi-shield", accent: "rose", eyebrow: "Perfil de acesso", title: (r) => r.name || "Perfil" },
  generic: { icon: "pi-folder-open", accent: "slate", eyebrow: "Registro" },
};

/** Retorna a meta do tipo com defaults garantidos (icon/accent/eyebrow/metrics). */
export function detailMetaFor(endpoint) {
  const base = { icon: "pi-folder-open", accent: "slate", eyebrow: "Registro", metrics: [], title: null, subtitle: null, badge: null };
  return { ...base, ...(DETAIL_META[resolveDetailType(endpoint)] || {}) };
}
