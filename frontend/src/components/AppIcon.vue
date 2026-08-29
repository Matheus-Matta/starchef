<template>
  <i
    :class="iconClass"
    :style="{ fontSize: iconSize, width: iconSize, height: iconSize }"
    :role="label ? 'img' : undefined"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
    :title="label || undefined"
  />
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 18 },
  // Rótulo acessível: quando informado, o ícone é anunciado por leitores de tela
  // e ganha tooltip. Sem rótulo, é decorativo (aria-hidden) — o padrão.
  label: { type: String, default: "" },
});

// Ícones do frontend limitados a 0,8rem (~12,8px) para um visual mais compacto.
// O `size` (px) do chamador é respeitado apenas quando menor, então nada aumenta —
// só reduz os ícones grandes para 0,8rem.
const MAX_ICON_PX = 12.8; // 0.8rem @ base 16px
const iconSize = computed(() => `${Math.min(props.size, MAX_ICON_PX)}px`);

const icons = {
  "alert-circle": "pi-exclamation-circle",
  "armchair": "pi-th-large",
  "arrow-right": "pi-arrow-right",
  "arrow-left": "pi-arrow-left",
  "bar-chart-3": "pi-chart-bar",
  "bell": "pi-bell",
  "bike": "pi-send",
  "book-open": "pi-book",
  "book-marked": "pi-bookmark",
  "calculator": "pi-calculator",
  "check": "pi-check",
  "check-check": "pi-check-circle",
  "check-circle": "pi-check-circle",
  "chevron-down": "pi-chevron-down",
  "chevron-right": "pi-chevron-right",
  "chevrons-up-down": "pi-sort-alt",
  "circle-dot": "pi-circle-fill",
  "clipboard-list": "pi-list-check",
  "clock": "pi-clock",
  "close": "pi-times",
  "credit-card": "pi-credit-card",
  "dollar-sign": "pi-dollar",
  "download": "pi-download",
  "edit": "pi-pencil",
  "eye": "pi-eye",
  "eye-off": "pi-eye-slash",
  "filter": "pi-filter",
  "flask": "pi-filter-fill",
  "hash": "pi-hashtag",
  "hourglass": "pi-hourglass",
  "home": "pi-home",
  "layers": "pi-clone",
  "layout-dashboard": "pi-chart-pie",
  "life-buoy": "pi-question-circle",
  "log-out": "pi-sign-out",
  "lock": "pi-lock",
  "mail": "pi-envelope",
  "map-pin": "pi-map-marker",
  "minus": "pi-minus",
  "money": "pi-money-bill",
  "moon": "pi-moon",
  "package": "pi-box",
  "panel-left": "pi-bars",
  "percentage": "pi-percentage",
  "play": "pi-play",
  "plus": "pi-plus",
  "qrcode": "pi-qrcode",
  "receipt-text": "pi-receipt",
  "refresh": "pi-refresh",
  "salad": "pi-palette",
  "scale": "pi-gauge",
  "save": "pi-save",
  "search": "pi-search",
  "settings": "pi-cog",
  "shield-check": "pi-shield",
  "shopping-bag": "pi-shopping-bag",
  "shopping-cart": "pi-shopping-cart",
  "soup": "pi-shop",
  "star": "pi-star",
  "store": "pi-building",
  "sun": "pi-sun",
  "tag": "pi-tag",
  "ticket": "pi-ticket",
  "timer": "pi-stopwatch",
  "trash": "pi-trash",
  "monitor": "pi-desktop",
  "trending-up": "pi-chart-line",
  "truck": "pi-truck",
  "user-cog": "pi-user-edit",
  "users": "pi-users",
  "wallet": "pi-wallet",
  "warning": "pi-exclamation-triangle",
  "x": "pi-times",
  "zap": "pi-bolt",
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
