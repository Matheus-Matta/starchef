<template>
  <i :class="iconClass" :style="{ fontSize: `${size}px`, width: `${size}px`, height: `${size}px` }" aria-hidden="true" />
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 18 },
});

const icons = {
  "armchair": "pi-th-large",
  "arrow-right": "pi-arrow-right",
  "bar-chart-3": "pi-chart-bar",
  "bell": "pi-bell",
  "book-open": "pi-book",
  "check": "pi-check",
  "check-check": "pi-check-circle",
  "chevron-down": "pi-chevron-down",
  "chevrons-up-down": "pi-sort-alt",
  "clock": "pi-clock",
  "dollar-sign": "pi-dollar",
  "eye": "pi-eye",
  "eye-off": "pi-eye-slash",
  "layout-dashboard": "pi-chart-pie",
  "life-buoy": "pi-question-circle",
  "lock": "pi-lock",
  "mail": "pi-envelope",
  "moon": "pi-moon",
  "package": "pi-box",
  "panel-left": "pi-bars",
  "play": "pi-play",
  "plus": "pi-plus",
  "receipt-text": "pi-receipt",
  "search": "pi-search",
  "shield-check": "pi-shield",
  "soup": "pi-shop",
  "store": "pi-building",
  "sun": "pi-sun",
  "timer": "pi-stopwatch",
  "trending-up": "pi-chart-line",
  "user-cog": "pi-user-edit",
  "users": "pi-users",
  "wallet": "pi-wallet",
};

const iconClass = computed(() => `pi ${icons[props.name] || "pi-circle"}`);
</script>

<style scoped>
i {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
</style>
