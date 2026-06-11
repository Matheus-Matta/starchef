<template>
  <span class="sc-badge" :style="[badgeStyle, style]">
    <span v-if="dot" class="sc-badge__dot" :style="{ background: solid ? 'currentColor' : toneStyle.dot }" />
    <span v-if="$slots.icon" class="sc-badge__icon">
      <slot name="icon" />
    </span>
    <slot />
  </span>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  tone: { type: String, default: "neutral" },
  size: { type: String, default: "md" },
  dot: { type: Boolean, default: false },
  solid: { type: Boolean, default: false },
  style: { type: Object, default: () => ({}) },
});

const tones = {
  neutral: { bg: "var(--surface-sunken)", fg: "var(--text-muted)", dot: "var(--text-subtle)" },
  brand: { bg: "var(--brand-subtle)", fg: "var(--text-brand)", dot: "var(--brand)" },
  success: { bg: "var(--success-subtle)", fg: "var(--success-text)", dot: "var(--success)" },
  warning: { bg: "var(--warning-subtle)", fg: "var(--warning-text)", dot: "var(--warning)" },
  danger: { bg: "var(--danger-subtle)", fg: "var(--danger-text)", dot: "var(--danger)" },
  info: { bg: "var(--info-subtle)", fg: "var(--info-text)", dot: "var(--info)" },
};

const toneStyle = computed(() => tones[props.tone] || tones.neutral);
const isSmall = computed(() => props.size === "sm");

const badgeStyle = computed(() => ({
  gap: isSmall.value ? "5px" : "6px",
  height: isSmall.value ? "20px" : "24px",
  padding: isSmall.value ? "0 8px" : "0 10px",
  background: props.solid ? toneStyle.value.dot : toneStyle.value.bg,
  color: props.solid ? (props.tone === "neutral" ? "var(--text-on-inverse)" : "#fff") : toneStyle.value.fg,
  font: `var(--weight-semibold) ${isSmall.value ? "var(--text-2xs)" : "var(--text-xs)"}/1 var(--font-sans)`,
}));
</script>

<style scoped>
.sc-badge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-pill);
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.sc-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sc-badge__icon {
  display: inline-flex;
  font-size: 13px;
}
</style>
