<template>
  <div class="app-shell" :class="{ 'app-shell--nav-open': mobileNavOpen }" :data-theme="theme">
    <Sidebar
      :active="activeKey"
      :collapsed="isMobile ? false : sidebarCollapsed"
      :mobile-open="mobileNavOpen"
      :user="auth.user"
      :stats="sidebarStats"
      :restaurants="restaurants"
      :selected-restaurant-id="selectedRestaurantId"
      :scope="currentScope"
      :theme="theme"
      @navigate="navigate"
      @scope-change="setRestaurantScope"
      @close="closeMobileNav"
      @toggle-theme="toggleTheme"
      @logout="logout"
    />
    <div class="app-backdrop" :class="{ 'app-backdrop--visible': mobileNavOpen }" @click="closeMobileNav" />
    <main class="app-main">
      <Topbar
        :title="pageTitle"
        :theme="theme"
        :user="auth.user"
        :stats="sidebarStats"
        :scope="currentScope"
        @toggle-sidebar="onToggleSidebar"
        @toggle-theme="toggleTheme"
        @logout="logout"
      />
      <section class="app-content" :class="{ 'app-content--full': route.meta.fullWidth, 'app-content--mobile-nav': showMobileBottomNav }">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="routeViewKey" />
          </Transition>
        </RouterView>
      </section>
      <MobileBottomNav
        v-if="showMobileBottomNav"
        :active="activeKey"
        :can-create="canCreateHere"
        :create-label="mobileCreateLabel"
        :menu-open="mobileNavOpen"
        @navigate="navigate"
        @create="createFromCurrentRoute"
        @menu="mobileNavOpen = true"
      />
    </main>
  </div>
</template>

<script setup>
import { computed, inject, onErrorCaptured, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";

import Sidebar from "./Sidebar.vue";
import Topbar from "./Topbar.vue";
import MobileBottomNav from "../components/MobileBottomNav.vue";
import { resources } from "../config/resources";
import { api } from "../services/api";
import { useAuthStore } from "../stores/auth";
import { useNotificationsStore } from "../stores/notifications";
import { useRealtimeResource } from "../composables/useRealtimeResource";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const notifications = useNotificationsStore();
const sidebarCollapsed = ref(false);
const mobileNavOpen = ref(false);
const isMobile = ref(false);
let navMediaQuery = null;
const theme = inject("theme");
const dashboardSummary = ref(null);
const restaurants = ref([]);
const selectedRestaurantId = ref(localStorage.getItem("starchef-restaurant-scope") || "");
const scopeRefreshKey = ref(0);
let summaryTimer = null;
useRealtimeResource(
  ["orders.order", "orders.orderitem", "payments.payment"],
  () => loadDashboardSummary(),
  { debounce: 250 },
);

const activeKey = computed(() => route.meta.nav || route.name || "painel");
const currentResource = computed(() => resources.find((resource) => resource.name === route.name) || null);
const isPdvRoute = computed(() => ["pdv", "pedido-editar-itens"].includes(String(route.name)));
const showMobileBottomNav = computed(() => {
  return (String(route.name) === "painel" || String(route.name).startsWith("relatorio")) || Boolean(currentResource.value);
});
const canCreateHere = computed(() => {
  if (currentResource.value) return Boolean(currentResource.value.formFields || currentResource.value.pro?.primaryAction);
  return !String(route.name).endsWith("--create") && !String(route.name).endsWith("--edit");
});
const mobileCreateLabel = computed(() => {
  const label = currentResource.value?.pro?.primaryAction?.label;
  if (label) return label.replace(/^Novo\s+/i, "Novo ");
  if (isPdvRoute.value) return "Novo pedido";
  return currentResource.value?.formFields ? "Novo" : canCreateHere.value ? "Novo pedido" : "Criar";
});
const pageTitle = computed(() => route.meta.title || "StarChef");
const sidebarStats = computed(() => ({
  ordersOpen: dashboardSummary.value?.open_orders ?? 0,
  ordersToday: dashboardSummary.value?.orders_count ?? 0,
  kitchenOpen: dashboardSummary.value?.kitchen_open_items ?? dashboardSummary.value?.open_orders ?? 0,
}));
const canSeeAllRestaurants = computed(() => Boolean(auth.user?.is_superuser || auth.user?.profile_type === "admin"));
const selectedRestaurant = computed(() => restaurants.value.find((restaurant) => restaurant.id === selectedRestaurantId.value) || null);
const routeViewKey = computed(() => {
  // A etapa do PDV usa a URL para alimentar o histórico do botão Voltar, mas
  // não deve remontar o componente e perder o pedido que está sendo montado.
  if (isPdvRoute.value) {
    const query = { ...route.query };
    delete query.step;
    delete query.order;
    return `${route.path}:${JSON.stringify(query)}:${selectedRestaurantId.value || "all"}:${scopeRefreshKey.value}`;
  }
  return `${route.fullPath}:${selectedRestaurantId.value || "all"}:${scopeRefreshKey.value}`;
});
const currentScope = computed(() => {
  if (canSeeAllRestaurants.value && !selectedRestaurantId.value) {
    return {
      restaurantName: "Todos os restaurantes",
      branchName: "Todas as filiais",
      isAllRestaurants: true,
    };
  }

  return {
    restaurantName: selectedRestaurant.value?.trade_name || auth.user?.restaurant_name || auth.user?.account_name || "Restaurante",
    branchName: selectedRestaurant.value ? "Todas as filiais" : auth.user?.branch_name || "Todas as filiais",
    isAllRestaurants: false,
  };
});

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

function navigate(name) {
  router.push({ name });
  closeMobileNav();
}

function createFromCurrentRoute() {
  const resource = currentResource.value;
  if (!resource) {
    if (!canCreateHere.value) return;
    router.push({ name: "pdv", query: { new: Date.now() } });
    return;
  }
  const primary = resource.pro?.primaryAction;
  if (primary?.route) {
    router.push({ name: primary.route });
    return;
  }
  if (resource.formFields) router.push({ name: `${resource.name}--create` });
}

// O botão de menu da topbar tem dois papéis: no desktop colapsa a sidebar
// para o modo mini; no mobile/tablet-retrato abre/fecha o drawer off-canvas.
function onToggleSidebar() {
  if (isMobile.value) mobileNavOpen.value = !mobileNavOpen.value;
  else sidebarCollapsed.value = !sidebarCollapsed.value;
}

function closeMobileNav() {
  mobileNavOpen.value = false;
}

function handleNavMediaChange(event) {
  isMobile.value = event.matches;
  // Ao voltar para o desktop, garante que o drawer não fique preso aberto.
  if (!event.matches) mobileNavOpen.value = false;
}

async function loadDashboardSummary() {
  try {
    const params = {};
    if (canSeeAllRestaurants.value && selectedRestaurantId.value) {
      params.restaurant = selectedRestaurantId.value;
    }
    const response = await api.get("/reports/dashboard/", { params });
    dashboardSummary.value = response.data;
  } catch {
    dashboardSummary.value = null;
  }
}

async function loadRestaurants() {
  if (!canSeeAllRestaurants.value) {
    restaurants.value = [];
    selectedRestaurantId.value = "";
    localStorage.removeItem("starchef-restaurant-scope");
    return;
  }

  try {
    const response = await api.get("/restaurants/", { skipRestaurantScope: true });
    restaurants.value = response.data.results || response.data || [];
    if (selectedRestaurantId.value && !restaurants.value.some((restaurant) => restaurant.id === selectedRestaurantId.value)) {
      setRestaurantScope("");
    }
  } catch {
    restaurants.value = [];
  }
}

function setRestaurantScope(restaurantId) {
  selectedRestaurantId.value = restaurantId || "";
  if (selectedRestaurantId.value) {
    localStorage.setItem("starchef-restaurant-scope", selectedRestaurantId.value);
  } else {
    localStorage.removeItem("starchef-restaurant-scope");
  }
  scopeRefreshKey.value += 1;
  loadDashboardSummary();
}

async function logout() {
  notifications.reset();
  await auth.logout();
  router.push({ name: "login" });
}

onErrorCaptured((err) => {
  if (import.meta.env.DEV) console.warn("[AppLayout] captured render error:", err);
  return false;
});

onMounted(() => {
  navMediaQuery = window.matchMedia("(max-width: 900px)");
  isMobile.value = navMediaQuery.matches;
  navMediaQuery.addEventListener("change", handleNavMediaChange);
  loadRestaurants();
  loadDashboardSummary();
  summaryTimer = window.setInterval(loadDashboardSummary, 30000);
  notifications.init();
});

onUnmounted(() => {
  if (navMediaQuery) navMediaQuery.removeEventListener("change", handleNavMediaChange);
  if (summaryTimer) window.clearInterval(summaryTimer);
  notifications.reset();
});

// Fecha o drawer sempre que a rota muda (inclui navegações disparadas de
// dentro das telas, não apenas pelo menu lateral).
watch(() => route.fullPath, closeMobileNav);

watch(
  () => auth.user?.id,
  () => {
    loadRestaurants();
    loadDashboardSummary();
  },
);
</script>
