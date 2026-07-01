<template>
  <RouterView />
</template>

<script setup>
import { provide, ref, watchEffect } from "vue";
import { RouterView } from "vue-router";

const theme = ref(localStorage.getItem("starchef-theme") || "light");

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("starchef-theme", theme.value);
});

provide("theme", theme);
</script>
