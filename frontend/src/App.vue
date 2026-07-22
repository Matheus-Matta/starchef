<template>
  <RouterView />
  <Toast position="top-right" />
  <ConfirmDialog />
</template>

<script setup>
import { provide, ref, watchEffect } from "vue";
import { RouterView } from "vue-router";
import Toast from "primevue/toast";
import ConfirmDialog from "primevue/confirmdialog";

const theme = ref(localStorage.getItem("starchef-theme") || "light");

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("starchef-theme", theme.value);
});

provide("theme", theme);
</script>
