import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../layout/AppLayout.vue";
import { useAuthStore } from "../stores/auth";
import DashboardView from "../views/DashboardView.vue";
import KdsView from "../views/KdsView.vue";
import LoginScreen from "../views/LoginScreen.vue";
import PdvView from "../views/PdvView.vue";
import ReportsView from "../views/ReportsView.vue";
import ResourceFormView from "../views/ResourceFormView.vue";
import ResourceListView from "../views/ResourceListView.vue";

const orderType = {
  table: "Mesa",
  command: "Comanda",
  counter: "Balcao",
  delivery: "Delivery",
  takeaway: "Retirada",
  internal: "Interno",
};
const orderStatus = {
  open: "Aberto",
  sent_to_kitchen: "Cozinha",
  preparing: "Preparo",
  partially_ready: "Parcial",
  ready: "Pronto",
  delivered: "Entregue",
  awaiting_payment: "Pagamento",
  paid: "Pago",
  cancelled: "Cancelado",
  refunded: "Estornado",
};
const tableStatus = { free: "Livre", occupied: "Ocupada", reserved: "Reservada", cleaning: "Limpeza" };
const profileType = {
  admin: "Admin",
  owner: "Proprietario",
  manager: "Gerente",
  waiter: "Garcom",
  kitchen: "Cozinha",
  cashier: "Caixa",
  driver: "Entregador",
};
const movementType = { in: "Entrada", out: "Saida", adjustment: "Ajuste", sale: "Venda", inventory: "Inventario" };
const vehicleType = { bike: "Bicicleta", motorcycle: "Moto", car: "Carro", foot: "A pe" };
const menuChannel = { all: "Todos", table: "Salao", delivery: "Delivery", counter: "Balcao", digital: "Digital" };

// Reusable form option lists
const _sectorOpts = [
  { label: "Cozinha", value: "kitchen" },
  { label: "Bar", value: "bar" },
  { label: "Sobremesa", value: "dessert" },
];
const _unitOpts = [
  { label: "kg", value: "kg" },
  { label: "g", value: "g" },
  { label: "L", value: "L" },
  { label: "ml", value: "ml" },
  { label: "un", value: "un" },
  { label: "pct", value: "pct" },
  { label: "cx", value: "cx" },
];
const _channelOpts = [
  { label: "Todos", value: "all" },
  { label: "Salao", value: "table" },
  { label: "Delivery", value: "delivery" },
  { label: "Balcao", value: "counter" },
  { label: "Digital", value: "digital" },
];
const _vehicleOpts = [
  { label: "Bicicleta", value: "bike" },
  { label: "Moto", value: "motorcycle" },
  { label: "Carro", value: "car" },
  { label: "A pe", value: "foot" },
];
const _paymentTypeOpts = [
  { label: "Dinheiro", value: "cash" },
  { label: "Cartao de Credito", value: "credit_card" },
  { label: "Cartao de Debito", value: "debit_card" },
  { label: "PIX", value: "pix" },
  { label: "Voucher Refeicao", value: "voucher" },
  { label: "Outro", value: "other" },
];
const _printerDriverOpts = [
  { label: "Rede (TCP/IP)", value: "network" },
  { label: "USB", value: "usb" },
  { label: "Serial", value: "serial" },
];
const _stockTimingOpts = [
  { label: "No pagamento", value: "payment" },
  { label: "Na cozinha", value: "kitchen" },
];

const listRoutes = [
  // Operacional
  {
    name: "pedidos",
    title: "Pedidos",
    endpoint: "/orders/",
    columns: [
      { key: "sequence", label: "Pedido" },
      { key: "order_type", label: "Tipo", map: orderType },
      { key: "table_number", label: "Mesa" },
      { key: "customer_name", label: "Cliente" },
      { key: "total", label: "Total", type: "money", align: "right" },
      { key: "status", label: "Status", type: "status", map: orderStatus },
      { key: "opened_at", label: "Aberto", type: "date" },
    ],
  },
  {
    name: "kds-estacoes",
    title: "Estacoes KDS",
    endpoint: "/kitchen/stations/",
    columns: [
      { key: "name", label: "Estacao" },
      { key: "restaurant_name", label: "Restaurante" },
      { key: "branch_name", label: "Filial" },
      { key: "sla_minutes", label: "SLA (min)", align: "right" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome da estacao", type: "text", required: true },
      { name: "restaurant", label: "Restaurante", type: "remote-dropdown", endpoint: "/restaurants/", optionLabel: "trade_name", optionValue: "id" },
      { name: "sla_minutes", label: "SLA em minutos", type: "number", default: 15 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "mesas",
    title: "Mesas & Comandas",
    endpoint: "/tables/",
    columns: [
      { key: "number", label: "Mesa" },
      { key: "sector_name", label: "Setor" },
      { key: "capacity", label: "Lugares" },
      { key: "status", label: "Status", type: "status", map: tableStatus },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "number", label: "Numero da mesa", type: "text", required: true },
      { name: "capacity", label: "Capacidade (lugares)", type: "number", default: 4 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "clientes",
    title: "Clientes",
    endpoint: "/customers/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "phone", label: "Telefone" },
      { key: "email", label: "Email" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome completo", type: "text", required: true },
      { name: "phone", label: "Telefone", type: "text" },
      { name: "email", label: "Email", type: "text", inputType: "email" },
      { name: "notes", label: "Observacoes", type: "textarea", full: true },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "caixa",
    title: "Caixa",
    endpoint: "/cash-register/",
    columns: [
      { key: "status", label: "Status", type: "status", map: { open: "Aberto", closed: "Fechado" } },
      { key: "opening_amount", label: "Abertura", type: "money", align: "right" },
      { key: "expected_amount", label: "Esperado", type: "money", align: "right" },
      { key: "opened_at", label: "Aberto em", type: "date" },
      { key: "closed_at", label: "Fechado em", type: "date" },
    ],
  },
  // Cardapio
  {
    name: "cardapio",
    title: "Produtos",
    endpoint: "/menu/products/",
    columns: [
      { key: "internal_code", label: "Codigo" },
      { key: "name", label: "Produto" },
      { key: "category_name", label: "Categoria" },
      { key: "current_price", label: "Preco", type: "money", align: "right" },
      { key: "production_sector", label: "Setor" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do produto", type: "text", required: true, full: true },
      { name: "internal_code", label: "Codigo interno", type: "text" },
      { name: "current_price", label: "Preco (R$)", type: "decimal", required: true },
      { name: "production_sector", label: "Setor de producao", type: "dropdown", options: _sectorOpts },
      { name: "description", label: "Descricao", type: "textarea", full: true },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "categorias",
    title: "Categorias",
    endpoint: "/menu/categories/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "display_order", label: "Ordem" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "display_order", label: "Ordem de exibicao", type: "number", default: 0 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "ingredientes",
    title: "Ingredientes",
    endpoint: "/menu/ingredients/",
    columns: [
      { key: "name", label: "Ingrediente" },
      { key: "unit", label: "Unidade" },
      { key: "average_cost", label: "Custo medio", type: "money", align: "right" },
      { key: "minimum_stock", label: "Estoque min.", align: "right" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "unit", label: "Unidade de medida", type: "dropdown", options: _unitOpts },
      { name: "minimum_stock", label: "Estoque minimo", type: "decimal" },
      { name: "average_cost", label: "Custo medio (R$)", type: "decimal" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "receitas",
    title: "Receitas",
    endpoint: "/menu/recipes/",
    columns: [
      { key: "product.name", label: "Produto" },
      { key: "yield_quantity", label: "Rendimento" },
      { key: "total_cost", label: "Custo total", type: "money", align: "right" },
      { key: "auto_deduct_stock", label: "Baixa auto.", type: "boolean" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
  },
  {
    name: "cardapios",
    title: "Cardapios",
    endpoint: "/menu/menus/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "slug", label: "Slug" },
      { key: "channel", label: "Canal", map: menuChannel },
      { key: "available_from", label: "Disponivel de" },
      { key: "available_until", label: "Disponivel ate" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "slug", label: "Slug (URL)", type: "text", placeholder: "ex: almoco-segunda" },
      { name: "channel", label: "Canal", type: "dropdown", options: _channelOpts },
      { name: "available_from", label: "Disponivel de (HH:MM)", type: "text", placeholder: "08:00" },
      { name: "available_until", label: "Disponivel ate (HH:MM)", type: "text", placeholder: "22:00" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "adicionais",
    title: "Adicionais",
    endpoint: "/menu/addons/",
    columns: [
      { key: "name", label: "Adicional" },
      { key: "price", label: "Preco", type: "money", align: "right" },
      { key: "production_sector", label: "Setor" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "price", label: "Preco (R$)", type: "decimal", required: true },
      { name: "production_sector", label: "Setor", type: "dropdown", options: _sectorOpts },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  // Estoque
  {
    name: "estoque",
    title: "Estoque",
    endpoint: "/stock/movements/",
    columns: [
      { key: "ingredient_name", label: "Ingrediente" },
      { key: "location_name", label: "Local" },
      { key: "movement_type", label: "Movimento", type: "status", map: movementType },
      { key: "quantity", label: "Qtd.", align: "right" },
      { key: "total_cost", label: "Custo", type: "money", align: "right" },
      { key: "created_at", label: "Data", type: "date" },
    ],
  },
  {
    name: "locais-estoque",
    title: "Locais de Estoque",
    endpoint: "/stock/locations/",
    columns: [
      { key: "name", label: "Local" },
      { key: "description", label: "Descricao" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome do local", type: "text", required: true },
      { name: "description", label: "Descricao", type: "textarea", full: true },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  // Delivery
  {
    name: "zonas-entrega",
    title: "Zonas de Entrega",
    endpoint: "/delivery/zones/",
    columns: [
      { key: "name", label: "Zona" },
      { key: "min_radius_km", label: "Raio min. (km)", align: "right" },
      { key: "max_radius_km", label: "Raio max. (km)", align: "right" },
      { key: "delivery_fee", label: "Taxa", type: "money", align: "right" },
      { key: "estimated_minutes", label: "Tempo (min)", align: "right" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome da zona", type: "text", required: true },
      { name: "min_radius_km", label: "Raio minimo (km)", type: "decimal" },
      { name: "max_radius_km", label: "Raio maximo (km)", type: "decimal" },
      { name: "delivery_fee", label: "Taxa de entrega (R$)", type: "decimal" },
      { name: "estimated_minutes", label: "Tempo estimado (min)", type: "number" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "entregadores",
    title: "Entregadores",
    endpoint: "/delivery/deliverymen/",
    columns: [
      { key: "name", label: "Nome" },
      { key: "phone", label: "Telefone" },
      { key: "vehicle_type", label: "Veiculo", map: vehicleType },
      { key: "vehicle_plate", label: "Placa" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome completo", type: "text", required: true },
      { name: "phone", label: "Telefone", type: "text" },
      { name: "vehicle_type", label: "Tipo de veiculo", type: "dropdown", options: _vehicleOpts },
      { name: "vehicle_plate", label: "Placa", type: "text" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  // Pagamentos
  {
    name: "formas-pagamento",
    title: "Formas de Pagamento",
    endpoint: "/payments/methods/",
    globalScope: true,
    columns: [
      { key: "name", label: "Forma" },
      { key: "payment_type", label: "Tipo" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "payment_type", label: "Tipo de pagamento", type: "dropdown", options: _paymentTypeOpts },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "pagamentos",
    title: "Historico de Pagamentos",
    endpoint: "/payments/",
    globalScope: true,
    columns: [
      { key: "order", label: "Pedido" },
      { key: "payment_method.name", label: "Forma" },
      { key: "amount", label: "Valor", type: "money", align: "right" },
      { key: "change_amount", label: "Troco", type: "money", align: "right" },
      { key: "created_at", label: "Data", type: "date" },
    ],
  },
  // Fiscal
  {
    name: "notas-fiscais",
    title: "Notas Fiscais",
    endpoint: "/invoices/",
    globalScope: true,
    columns: [
      { key: "number", label: "Numero" },
      { key: "phase", label: "Tipo" },
      { key: "status", label: "Status", type: "status", map: { draft: "Rascunho", issued: "Emitida", cancelled: "Cancelada", error: "Erro" } },
      { key: "total_amount", label: "Valor", type: "money", align: "right" },
      { key: "issued_at", label: "Emissao", type: "date" },
    ],
  },
  // Impressao
  {
    name: "impressoras",
    title: "Impressoras",
    endpoint: "/printers/",
    globalScope: true,
    columns: [
      { key: "name", label: "Nome" },
      { key: "driver_type", label: "Driver" },
      { key: "ip_address", label: "IP / Porta" },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome", type: "text", required: true },
      { name: "driver_type", label: "Driver", type: "dropdown", options: _printerDriverOpts },
      { name: "ip_address", label: "IP / Host", type: "text" },
      { name: "port", label: "Porta", type: "number", default: 9100 },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  // Gestao
  {
    name: "restaurantes",
    title: "Restaurantes",
    endpoint: "/restaurants/",
    globalScope: true,
    columns: [
      { key: "trade_name", label: "Nome fantasia" },
      { key: "legal_name", label: "Razao social" },
      { key: "city", label: "Cidade" },
      { key: "state", label: "UF" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "trade_name", label: "Nome fantasia", type: "text", required: true },
      { name: "legal_name", label: "Razao social", type: "text" },
      { name: "phone", label: "Telefone", type: "text" },
      { name: "email", label: "Email", type: "text", inputType: "email" },
      { name: "address", label: "Endereco", type: "text", full: true },
      { name: "city", label: "Cidade", type: "text" },
      { name: "state", label: "UF", type: "text", placeholder: "SP" },
      { name: "zip_code", label: "CEP", type: "text", placeholder: "00000-000" },
    ],
  },
  {
    name: "filiais",
    title: "Filiais",
    endpoint: "/branches/",
    globalScope: true,
    columns: [
      { key: "name", label: "Filial" },
      { key: "restaurant_name", label: "Restaurante" },
      { key: "city", label: "Cidade" },
      { key: "stock_deduction_timing", label: "Baixa estoque", map: { payment: "No pagamento", kitchen: "Na cozinha" } },
      { key: "is_active", label: "Ativa", type: "boolean" },
    ],
    formFields: [
      { name: "name", label: "Nome da filial", type: "text", required: true },
      { name: "phone", label: "Telefone", type: "text" },
      { name: "email", label: "Email", type: "text", inputType: "email" },
      { name: "address", label: "Endereco", type: "text", full: true },
      { name: "city", label: "Cidade", type: "text" },
      { name: "state", label: "UF", type: "text", placeholder: "SP" },
      { name: "zip_code", label: "CEP", type: "text", placeholder: "00000-000" },
      { name: "stock_deduction_timing", label: "Baixa de estoque", type: "dropdown", options: _stockTimingOpts },
      { name: "is_active", label: "Ativa", type: "boolean", default: true },
    ],
  },
  {
    name: "usuarios",
    title: "Usuarios",
    endpoint: "/users/",
    globalScope: true,
    columns: [
      { key: "username", label: "Usuario" },
      { key: "email", label: "Email" },
      { key: "first_name", label: "Nome" },
      { key: "profile.profile_type", label: "Perfil", type: "status", map: profileType },
      { key: "profile.branch_name", label: "Filial" },
      { key: "is_active", label: "Ativo", type: "boolean" },
    ],
    formFields: [
      { name: "username", label: "Nome de usuario", type: "text", required: true },
      { name: "email", label: "Email", type: "text", inputType: "email", required: true },
      { name: "first_name", label: "Nome", type: "text" },
      { name: "last_name", label: "Sobrenome", type: "text" },
      { name: "password", label: "Senha", type: "password" },
      { name: "is_active", label: "Ativo", type: "boolean", default: true },
    ],
  },
  {
    name: "perfis",
    title: "Perfis de Acesso",
    endpoint: "/roles/",
    globalScope: true,
    columns: [
      { key: "name", label: "Perfil" },
      { key: "description", label: "Descricao" },
      { key: "created_at", label: "Criado em", type: "date" },
    ],
    formFields: [
      { name: "name", label: "Nome do perfil", type: "text", required: true },
      { name: "description", label: "Descricao", type: "textarea", full: true },
    ],
  },
].flatMap((config) => {
  const listRoute = {
    path: config.name,
    name: config.name,
    component: ResourceListView,
    props: { ...config, subtitle: "API REST", formEnabled: !!config.formFields },
    meta: { requiresAuth: true, title: config.title, nav: config.name },
  };

  if (!config.formFields) return [listRoute];

  const formProps = {
    endpoint: config.endpoint,
    title: config.title,
    formFields: config.formFields,
    globalScope: !!config.globalScope,
  };

  return [
    listRoute,
    {
      path: `${config.name}/novo`,
      name: `${config.name}--novo`,
      component: ResourceFormView,
      props: { ...formProps },
      meta: { requiresAuth: true, title: `Novo — ${config.title}`, nav: config.name },
    },
    {
      path: `${config.name}/:id/editar`,
      name: `${config.name}--editar`,
      component: ResourceFormView,
      props: (route) => ({ ...formProps, id: route.params.id }),
      meta: { requiresAuth: true, title: `Editar — ${config.title}`, nav: config.name },
    },
  ];
});

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: LoginScreen,
      meta: { public: true, title: "Login" },
    },
    {
      path: "/",
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: { name: "painel" } },
        {
          path: "painel",
          name: "painel",
          component: DashboardView,
          meta: { requiresAuth: true, title: "Painel operacional", nav: "painel" },
        },
        {
          path: "pdv",
          name: "pdv",
          component: PdvView,
          meta: { requiresAuth: true, title: "PDV — Ponto de Venda", nav: "pdv" },
        },
        {
          path: "kds",
          name: "kds",
          component: KdsView,
          meta: { requiresAuth: true, title: "KDS Cozinha", nav: "kds" },
        },
        {
          path: "relatorios",
          name: "relatorios",
          component: ReportsView,
          meta: { requiresAuth: true, title: "Relatorios", nav: "relatorios" },
        },
        ...listRoutes,
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: { name: "painel" } },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta.public) {
    if (auth.isAuthenticated && (await auth.validateSession())) {
      return { name: "painel" };
    }
    return true;
  }

  if (to.matched.some((record) => record.meta.requiresAuth)) {
    const valid = await auth.validateSession();
    if (!valid) {
      return {
        name: "login",
        query: { next: to.fullPath },
      };
    }
  }

  return true;
});

window.addEventListener("auth:unauthorized", () => {
  const auth = useAuthStore();
  auth.clearSession();
  if (router.currentRoute.value.name !== "login") {
    router.push({
      name: "login",
      query: { next: router.currentRoute.value.fullPath },
    });
  }
});
