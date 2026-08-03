<template>
  <div class="sc-stat-card" :style="style">
    <div class="sc-stat-card__header">
      <span class="sc-stat-card__label">{{ label }}</span>
      <span v-if="$slots.icon" class="sc-stat-card__icon" :style="iconStyle">
        <slot name="icon" />
      </span>
    </div>
    <div class="sc-stat-card__value-row">
      <span class="num sc-stat-card__value">{{ value }}</span>
      <span v-if="delta != null" class="sc-stat-card__delta" :style="deltaStyle">
        <span class="sc-stat-card__delta-arrow">{{ deltaDir === "up" ? "▲" : "▼" }}</span>{{ delta }}
      </span>
    </div>
    <span v-if="caption" class="sc-stat-card__caption">{{ caption }}</span>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  tone: { type: String, default: "brand" },
  delta: { type: [String, Number], default: null },
  deltaDir: { type: String, default: "up" },
  caption: { type: String, default: "" },
  style: { type: Object, default: () => ({}) },
});

const tones = {
  brand: { bg: "var(--brand-subtle)", fg: "var(--brand)" },
  success: { bg: "var(--success-subtle)", fg: "var(--success)" },
  warning: { bg: "var(--warning-subtle)", fg: "var(--warning)" },
  danger: { bg: "var(--danger-subtle)", fg: "var(--danger)" },
  info: { bg: "var(--info-subtle)", fg: "var(--info)" },
};

const toneStyle = computed(() => tones[props.tone] || tones.brand);
const iconStyle = computed(() => ({ background: toneStyle.value.bg, color: toneStyle.value.fg }));
const deltaStyle = computed(() => {
  const up = props.deltaDir === "up";
  return {
    background: up ? "var(--success-subtle)" : "var(--danger-subtle)",
    color: up ? "var(--success-text)" : "var(--danger-text)",
  };
});
</script>

<style scoped>
.sc-stat-card {
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: soft-pop var(--motion-slow) var(--motion-spring) both;
  transition: transform var(--motion-base) var(--motion-spring), box-shadow var(--motion-base) ease, border-color var(--motion-base) ease;
}

.sc-stat-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--brand) 22%, var(--border));
  box-shadow: var(--shadow-md);
}

.sc-stat-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sc-stat-card__label {
  font: var(--font-label);
  color: var(--text-muted);
  letter-spacing: var(--tracking-snug);
}

.sc-stat-card__icon {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
}

.sc-stat-card__value-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.sc-stat-card__value {
  font: var(--weight-extra) var(--text-3xl) / 1 var(--font-sans);
  color: var(--text-strong);
  letter-spacing: var(--tracking-tight);
}

.sc-stat-card__delta {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--radius-pill);
  font: var(--weight-bold) var(--text-xs) / 1 var(--font-sans);
}

.sc-stat-card__delta-arrow {
  font-size: 13px;
  line-height: 1;
}

.sc-stat-card__caption {
  font: var(--font-caption);
  color: var(--text-subtle);
}

@media (max-width: 560px) {
  .sc-stat-card { padding: 14px; gap: 10px; min-width: 0; }
  .sc-stat-card:hover { transform: none; }
  .sc-stat-card__icon { width: 32px; height: 32px; font-size: 16px; }
  .sc-stat-card__label { font-size: 11px; line-height: 1.25; }
  .sc-stat-card__value { font-size: clamp(20px, 7vw, 27px); overflow-wrap: anywhere; }
  .sc-stat-card__caption { font-size: 11px; line-height: 1.3; }
}
</style>
