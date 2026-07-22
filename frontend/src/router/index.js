import { createRouter, createWebHistory } from "vue-router";

import { resources } from "../config/resources";
import AppLayout from "../layout/AppLayout.vue";
import { useAuthStore } from "../stores/auth";
import DashboardView from "../views/DashboardView.vue";
import KdsView from "../views/KdsView.vue";
import LoginScreen from "../views/LoginScreen.vue";
import PdvView from "../views/PdvView.vue";
import ReportsView from "../views/ReportsView.vue";
import ResourceFormView from "../views/ResourceFormView.vue";
import ResourceListView from "../views/ResourceListView.vue";

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
      component: ResourceListView,
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

const resourceRoutes = resources.flatMap(buildResourceRoutes);

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginScreen, meta: { public: true, title: "Login" } },
    {
      path: "/",
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: { name: "painel" } },
        { path: "painel", name: "painel", component: DashboardView, meta: { requiresAuth: true, title: "Painel operacional", nav: "painel" } },
        { path: "pdv", name: "pdv", component: PdvView, meta: { requiresAuth: true, title: "PDV — Ponto de Venda", nav: "pdv" } },
        { path: "kds", name: "kds", component: KdsView, meta: { requiresAuth: true, title: "KDS Cozinha", nav: "kds" } },
        { path: "relatorios", name: "relatorios", component: ReportsView, meta: { requiresAuth: true, title: "Relatorios", nav: "relatorios" } },
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
    const valid = await auth.validateSession();
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
    router.push({ name: "login", query: { next: router.currentRoute.value.fullPath } });
  }
});
