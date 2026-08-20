import { createRouter, createWebHistory } from "vue-router";

import { resources } from "../config/resources";
import { useAuthStore } from "../stores/auth";

const AppLayout = () => import("../layout/AppLayout.vue");
const DashboardView = () => import("../views/DashboardView.vue");
const HomeView = () => import("../views/HomeView.vue");
const KdsView = () => import("../views/KdsView.vue");
const LoginScreen = () => import("../views/LoginScreen.vue");
const PasswordRecoveryView = () => import("../views/PasswordRecoveryView.vue");
const PdvView = () => import("../views/PdvView.vue");
const OrderEditView = () => import("../views/OrderEditView.vue");
const CashRegisterView = () => import("../views/CashRegisterView.vue");
const ReportsView = () => import("../views/ReportsView.vue");
const KdsStationsView = () => import("../views/KdsStationsView.vue");
const ResourceFormView = () => import("../views/ResourceFormView.vue");
const ResourceListViewPro = () => import("../views/ResourceListViewPro.vue");

/**
 * Gera as rotas de um recurso a partir do seu schema (config/resources.js):
 *   - lista    /<name>
 *   - criar    /<name>/create          (apenas se houver formFields)
 *   - ver      /<name>/:id              (substitui o antigo drawer de detalhe)
 *   - editar   /<name>/:id/edit         (apenas se houver formFields)
 * A pagina de recurso (ResourceFormView) recebe `mode` para saber o que renderizar.
 */
function buildResourceRoutes(resource) {
  const pageProps = {
    endpoint: resource.endpoint,
    title: resource.title,
    columns: resource.columns,
    formFields: resource.formFields || null,
    globalScope: !!resource.globalScope,
    // Recursos compartilhados entre restaurantes (ex.: categorias, adicionais)
    // não exibem o seletor de restaurante nem herdam um automaticamente.
    sharedAcrossRestaurants: !!resource.sharedAcrossRestaurants,
  };
  const module = resource.module || "base";
  const meta = (title) => ({ requiresAuth: true, title, nav: resource.name, module });

  const routes = [
    {
      path: resource.name,
      name: resource.name,
      // Todas as listagens usam o novo padrão de tabela (Pro).
      component: ResourceListViewPro,
      props: { ...resource, subtitle: "API REST", formEnabled: !!resource.formFields },
      meta: meta(resource.title),
    },
  ];

  if (resource.formFields) {
    routes.push({
      path: `${resource.name}/create`,
      name: `${resource.name}--create`,
      component: ResourceFormView,
      props: { ...pageProps, mode: "create" },
      meta: meta(`Novo — ${resource.title}`),
    });
  }

  routes.push(
    {
      path: `${resource.name}/:id`,
      name: `${resource.name}--view`,
      component: ResourceFormView,
      props: (route) => ({ ...pageProps, id: route.params.id, mode: "view" }),
      meta: meta(`Detalhe — ${resource.title}`),
    },
    {
      path: `${resource.name}/:id/edit`,
      name: `${resource.name}--edit`,
      component: ResourceFormView,
      props: (route) => ({ ...pageProps, id: route.params.id, mode: "edit" }),
      meta: meta(`Editar — ${resource.title}`),
    },
  );

  return routes;
}

// "caixa" e "kds-estacoes" têm telas próprias (não usam o CRUD genérico).
const CUSTOM_RESOURCES = new Set(["caixa", "kds-estacoes"]);
const resourceRoutes = resources.filter((resource) => !CUSTOM_RESOURCES.has(resource.name)).flatMap(buildResourceRoutes);

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginScreen, meta: { public: true, title: "Login" } },
    { path: "/esqueci-senha", name: "forgot-password", component: PasswordRecoveryView, meta: { public: true, title: "Esqueci minha senha" } },
    { path: "/redefinir-senha", name: "reset-password", component: PasswordRecoveryView, meta: { public: true, title: "Redefinir senha" } },
    {
      path: "/",
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: { name: "painel" } },
        { path: "home", name: "painel", component: HomeView, meta: { requiresAuth: true, title: "Home", nav: "painel" } },
        { path: "relatorio-geral", name: "relatorio-geral", component: DashboardView, meta: { requiresAuth: true, title: "Relatório geral", nav: "relatorio-geral" } },
        { path: "pdv", name: "pdv", component: PdvView, meta: { requiresAuth: true, title: "PDV — Ponto de Venda", nav: "pdv" } },
        { path: "caixa", name: "caixa", component: CashRegisterView, meta: { requiresAuth: true, title: "Controle de caixa", nav: "caixa" } },
        { path: "pedidos/:id/editar-itens", name: "pedido-editar-itens", component: OrderEditView, props: true, meta: { requiresAuth: true, title: "Editar pedido", nav: "pedidos" } },
        { path: "kds", name: "kds", component: KdsView, meta: { requiresAuth: true, title: "KDS Cozinha", nav: "kds", fullWidth: true } },
        { path: "kds-estacoes", name: "kds-estacoes", component: KdsStationsView, meta: { requiresAuth: true, title: "Estações KDS", nav: "kds-estacoes" } },
        { path: "relatorios", name: "relatorios", redirect: { name: "relatorio-vendas" } },
        { path: "relatorios/vendas", name: "relatorio-vendas", component: ReportsView, props: { section: "sales" }, meta: { requiresAuth: true, title: "Relatório de vendas", nav: "relatorio-vendas" } },
        { path: "relatorios/pedidos", name: "relatorio-pedidos", component: ReportsView, props: { section: "orders" }, meta: { requiresAuth: true, title: "Relatório de pedidos", nav: "relatorio-pedidos" } },
        { path: "relatorios/produtos", name: "relatorio-produtos", component: ReportsView, props: { section: "product" }, meta: { requiresAuth: true, title: "Relatório de produtos", nav: "relatorio-produtos" } },
        { path: "relatorios/pagamentos", name: "relatorio-pagamentos", component: ReportsView, props: { section: "payment" }, meta: { requiresAuth: true, title: "Relatório de pagamentos", nav: "relatorio-pagamentos" } },
        { path: "relatorios/garcons", name: "relatorio-garcons", component: ReportsView, props: { section: "waiter" }, meta: { requiresAuth: true, title: "Relatório de garçons", nav: "relatorio-garcons" } },
        { path: "relatorios/restaurantes", name: "relatorio-restaurantes", component: ReportsView, props: { section: "restaurant" }, meta: { requiresAuth: true, title: "Relatório por restaurante", nav: "relatorio-restaurantes" } },
        { path: "relatorios/filiais", redirect: { name: "relatorio-restaurantes" } },
        ...resourceRoutes,
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: { name: "painel" } },
  ],
});

/** Guarda de rota: valida a sessao e redireciona conforme autenticacao. */
router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta.public) {
    if (auth.isAuthenticated && (await auth.validateSession())) {
      return { name: "painel" };
    }
    return true;
  }

  if (to.matched.some((record) => record.meta.requiresAuth)) {
    // Depois da validação inicial, a troca entre páginas é local e imediata.
    // As chamadas da própria tela continuam validando o cookie e o interceptor
    // encerra a sessão caso o servidor responda 401.
    const valid =
      auth.initialized && auth.isAuthenticated && auth.user
        ? true
        : await auth.validateSession();
    if (!valid) {
      return { name: "login", query: { next: to.fullPath } };
    }

    // Bloqueia acesso forcado via URL a rotas de modulos desabilitados.
    const routeModule = to.matched.map((record) => record.meta.module).filter(Boolean).pop();
    if (routeModule && !auth.hasModule(routeModule)) {
      return { name: "painel" };
    }
  }

  return true;
});

// Logout global disparado pelo interceptor do axios quando a sessao expira.
window.addEventListener("auth:unauthorized", () => {
  const auth = useAuthStore();
  auth.clearSession();
  if (router.currentRoute.value.name !== "login") {
    window.location.href = "/login?next=" + encodeURIComponent(router.currentRoute.value.fullPath);
  }
});
