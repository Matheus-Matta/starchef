import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../layout/AppLayout.vue";
import { useAuthStore } from "../stores/auth";
import DashboardView from "../views/DashboardView.vue";
import KdsView from "../views/KdsView.vue";
import LoginScreen from "../views/LoginScreen.vue";
import PlaceholderView from "../views/PlaceholderView.vue";

const placeholderRoutes = [
  ["pedidos", "Pedidos"],
  ["mesas", "Mesas & Comandas"],
  ["cardapio", "Cardápio"],
  ["caixa", "Caixa"],
  ["clientes", "Clientes"],
  ["estoque", "Estoque"],
  ["relatorios", "Relatórios"],
  ["restaurantes", "Restaurantes"],
  ["usuarios", "Usuários"],
].map(([name, title]) => ({
  path: name,
  name,
  component: PlaceholderView,
  props: { title, view: name },
  meta: { requiresAuth: true, title, nav: name },
}));

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
          path: "kds",
          name: "kds",
          component: KdsView,
          meta: { requiresAuth: true, title: "KDS Cozinha", nav: "kds" },
        },
        ...placeholderRoutes,
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
