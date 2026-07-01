<template>
  <div class="app-shell" :data-theme="theme">
    <Sidebar
      :active="activeKey"
      :collapsed="sidebarCollapsed"
      :user="auth.user"
      :stats="sidebarStats"
      :restaurants="restaurants"
      :selected-restaurant-id="selectedRestaurantId"
      :scope="currentScope"
      @navigate="navigate"
      @scope-change="setRestaurantScope"
    />
    <main class="app-main">
      <Topbar
        :title="pageTitle"
        :theme="theme"
        :user="auth.user"
        :stats="sidebarStats"
        :scope="currentScope"
        @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
        @toggle-theme="toggleTheme"
        @new-order="router.push({ name: 'pdv' })"
        @logout="logout"
      />
      <section class="app-content">
        <RouterView :key="routeViewKey" />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, inject, onErrorCaptured, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";

import Sidebar from "./Sidebar.vue";
import Topbar from "./Topbar.vue";
import { api } from "../services/api";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const sidebarCollapsed = ref(false);
const theme = inject("theme");
const dashboardSummary = ref(null);
const restaurants = ref([]);
const selectedRestaurantId = ref(localStorage.getItem("starchef-restaurant-scope") || "");
const scopeRefreshKey = ref(0);
let summaryTimer = null;

const activeKey = computed(() => route.meta.nav || route.name || "painel");
const pageTitle = computed(() => route.meta.title || "StarChef");
const sidebarStats = computed(() => ({
  ordersOpen: dashboardSummary.value?.open_orders ?? 0,
  ordersToday: dashboardSummary.value?.orders_count ?? 0,
  kitchenOpen: dashboardSummary.value?.kitchen_open_items ?? dashboardSummary.value?.open_orders ?? 0,
}));
const canSeeAllRestaurants = computed(() => Boolean(auth.user?.is_superuser || auth.user?.profile_type === "admin"));
const selectedRestaurant = computed(() => restaurants.value.find((restaurant) => restaurant.id === selectedRestaurantId.value) || null);
const routeViewKey = computed(() => `${route.fullPath}:${selectedRestaurantId.value || "all"}:${scopeRefreshKey.value}`);
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
  await auth.logout();
  router.push({ name: "login" });
}

onErrorCaptured((err) => {
  if (import.meta.env.DEV) console.warn("[AppLayout] captured render error:", err);
  return false;
});

onMounted(() => {
  loadRestaurants();
  loadDashboardSummary();
  summaryTimer = window.setInterval(loadDashboardSummary, 30000);
});

onUnmounted(() => {
  if (summaryTimer) window.clearInterval(summaryTimer);
});

watch(
  () => auth.user?.id,
  () => {
    loadRestaurants();
    loadDashboardSummary();
  },
);
</script>
