<template>
  <Transition name="route-progress">
    <div v-if="routeLoading" class="app-route-progress" aria-label="Carregando página" />
  </Transition>
  <RouterView />
  <Toast position="top-right" />
  <ConfirmDialog />
</template>

<script setup>
import { onBeforeUnmount, provide, ref, watchEffect } from "vue";
import { RouterView } from "vue-router";
import Toast from "primevue/toast";
import ConfirmDialog from "primevue/confirmdialog";
import { useToast } from "primevue/usetoast";
import { router } from "./router";
import { useGlobalErrorHandler } from "./composables/useGlobalErrorHandler";

useGlobalErrorHandler(useToast());

const theme = ref(localStorage.getItem("starchef-theme") || "light");
const routeLoading = ref(false);
const removeBeforeHook = router.beforeEach(() => {
  routeLoading.value = true;
});
const removeAfterHook = router.afterEach(() => {
  window.requestAnimationFrame(() => { routeLoading.value = false; });
});

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("starchef-theme", theme.value);
});

provide("theme", theme);
onBeforeUnmount(() => {
  removeBeforeHook();
  removeAfterHook();
});
</script>
