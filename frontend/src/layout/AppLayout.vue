<template>
  <div class="app-shell" :data-theme="theme">
    <Sidebar :active="activeKey" :collapsed="sidebarCollapsed" branch="Cantina da Ana" @navigate="navigate" />
    <main class="app-main">
      <Topbar
        :title="pageTitle"
        :theme="theme"
        :user="auth.user"
        @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
        @toggle-theme="toggleTheme"
        @new-order="router.push({ name: 'pedidos' })"
        @logout="logout"
      />
      <section class="app-content">
        <RouterView />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watchEffect } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";

import Sidebar from "./Sidebar.vue";
import Topbar from "./Topbar.vue";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const sidebarCollapsed = ref(false);
const theme = ref(localStorage.getItem("starchef-theme") || "light");

const activeKey = computed(() => route.meta.nav || route.name || "painel");
const pageTitle = computed(() => route.meta.title || "StarChef");

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("starchef-theme", theme.value);
});

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

function navigate(name) {
  router.push({ name });
}

async function logout() {
  await auth.logout();
  router.push({ name: "login" });
}
</script>
