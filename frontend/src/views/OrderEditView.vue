<template>
  <PdvView edit-mode :order-id="id" />
</template>

<script setup>
import PdvView from "./PdvView.vue";

defineProps({ id: { type: String, required: true } });
</script>
