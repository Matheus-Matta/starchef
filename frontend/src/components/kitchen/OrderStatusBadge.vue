<template>
  <span class="sc-order-status" :style="[badgeStyle, style]">
    <span class="sc-order-status__dot" :style="{ animation: animated ? 'sc-pulse 1.4s var(--ease-in-out) infinite' : 'none' }" />
    {{ label || statusStyle.label }}
  </span>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, default: "new" },
  label: { type: String, default: "" },
  pulse: { type: Boolean, default: false },
  size: { type: String, default: "md" },
  style: { type: Object, default: () => ({}) },
});

const statuses = {
  new: { label: "Novo", fg: "var(--order-new)", bg: "var(--order-new-bg)" },
  prep: { label: "Preparo", fg: "var(--order-prep)", bg: "var(--order-prep-bg)" },
  ready: { label: "Pronto", fg: "var(--order-ready)", bg: "var(--order-ready-bg)" },
  done: { label: "Entregue", fg: "var(--order-done)", bg: "var(--order-done-bg)" },
  late: { label: "Atrasado", fg: "var(--danger)", bg: "var(--danger-subtle)" },
};

const statusStyle = computed(() => statuses[props.status] || statuses.new);
const isSmall = computed(() => props.size === "sm");
const animated = computed(() => props.pulse && (props.status === "new" || props.status === "late"));
const badgeStyle = computed(() => ({
  gap: isSmall.value ? "5px" : "7px",
  height: isSmall.value ? "22px" : "28px",
  padding: isSmall.value ? "0 9px" : "0 12px",
  background: statusStyle.value.bg,
  color: statusStyle.value.fg,
  font: `var(--weight-bold) ${isSmall.value ? "var(--text-2xs)" : "var(--text-xs)"}/1 var(--font-sans)`,
}));
</script>

<style scoped>
.sc-order-status {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-pill);
  letter-spacing: var(--tracking-snug);
  white-space: nowrap;
}

.sc-order-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

@keyframes sc-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.45;
    transform: scale(0.8);
  }
}
</style>
