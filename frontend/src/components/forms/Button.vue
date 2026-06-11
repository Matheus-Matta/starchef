<template>
  <button
    :type="type"
    :disabled="isDisabled"
    class="sc-button"
    :style="[buttonStyle, style]"
    @mouseenter="hover = true"
    @mouseleave="leave"
    @mousedown="pressed = true"
    @mouseup="pressed = false"
  >
    <span v-if="loading" class="sc-button__spinner" :style="{ width: `${sizeStyle.icon}px`, height: `${sizeStyle.icon}px` }" />
    <span v-else-if="$slots.icon" class="sc-button__icon" :style="{ fontSize: `${sizeStyle.icon}px` }">
      <slot name="icon" />
    </span>
    <span v-if="!iconOnly"><slot /></span>
    <span v-if="!loading && $slots.iconRight" class="sc-button__icon" :style="{ fontSize: `${sizeStyle.icon}px` }">
      <slot name="iconRight" />
    </span>
  </button>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  variant: { type: String, default: "primary" },
  size: { type: String, default: "md" },
  iconOnly: { type: Boolean, default: false },
  fullWidth: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: "button" },
  style: { type: Object, default: () => ({}) },
});

const hover = ref(false);
const pressed = ref(false);

const sizes = {
  sm: { height: "var(--control-sm)", padding: "0 12px", font: "var(--text-sm)", gap: "6px", icon: 15 },
  md: { height: "var(--control-md)", padding: "0 16px", font: "var(--text-base)", gap: "8px", icon: 17 },
  lg: { height: "var(--control-lg)", padding: "0 22px", font: "var(--text-md)", gap: "9px", icon: 19 },
};

const variants = {
  primary: {
    base: "var(--brand)",
    hover: "var(--brand-hover)",
    active: "var(--brand-active)",
    color: "var(--on-brand)",
    border: "1px solid transparent",
    shadow: "var(--shadow-brand)",
  },
  secondary: {
    base: "var(--surface-card)",
    hover: "var(--surface-hover)",
    active: "var(--surface-active)",
    color: "var(--text-strong)",
    border: "1px solid var(--border-strong)",
    shadow: "var(--shadow-xs)",
  },
  ghost: {
    base: "transparent",
    hover: "var(--surface-hover)",
    active: "var(--surface-active)",
    color: "var(--text-body)",
    border: "1px solid transparent",
    shadow: "none",
  },
  subtle: {
    base: "var(--brand-subtle)",
    hover: "var(--brand-subtle-2)",
    active: "var(--brand-subtle-2)",
    color: "var(--text-brand)",
    border: "1px solid transparent",
    shadow: "none",
  },
  danger: {
    base: "var(--danger)",
    hover: "color-mix(in srgb, var(--danger) 86%, #000)",
    active: "color-mix(in srgb, var(--danger) 74%, #000)",
    color: "#fff",
    border: "1px solid transparent",
    shadow: "none",
  },
  success: {
    base: "var(--success)",
    hover: "color-mix(in srgb, var(--success) 86%, #000)",
    active: "color-mix(in srgb, var(--success) 74%, #000)",
    color: "#fff",
    border: "1px solid transparent",
    shadow: "none",
  },
};

const sizeStyle = computed(() => sizes[props.size] || sizes.md);
const variantStyle = computed(() => variants[props.variant] || variants.primary);
const isDisabled = computed(() => props.disabled || props.loading);
const background = computed(() => {
  if (isDisabled.value) return variantStyle.value.base;
  if (pressed.value) return variantStyle.value.active;
  if (hover.value) return variantStyle.value.hover;
  return variantStyle.value.base;
});

const buttonStyle = computed(() => ({
  gap: sizeStyle.value.gap,
  height: sizeStyle.value.height,
  width: props.fullWidth ? "100%" : "auto",
  padding: props.iconOnly ? 0 : sizeStyle.value.padding,
  aspectRatio: props.iconOnly ? "1 / 1" : "auto",
  font: `var(--weight-semibold) ${sizeStyle.value.font}/1 var(--font-sans)`,
  cursor: isDisabled.value ? "not-allowed" : "pointer",
  opacity: isDisabled.value ? 0.55 : 1,
  transform: pressed.value && !isDisabled.value ? "translateY(0.5px) scale(0.99)" : "none",
  backgroundColor: background.value,
  color: variantStyle.value.color,
  border: variantStyle.value.border,
  boxShadow: variantStyle.value.shadow,
}));

function leave() {
  hover.value = false;
  pressed.value = false;
}
</script>

<style scoped>
.sc-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  letter-spacing: var(--tracking-snug);
  border-radius: var(--radius-md);
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
  white-space: nowrap;
}

.sc-button__icon {
  display: inline-flex;
}

.sc-button__spinner {
  display: inline-flex;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-top-color: transparent;
  animation: sc-spin 0.7s linear infinite;
}

@keyframes sc-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
