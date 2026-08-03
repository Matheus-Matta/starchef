<template>
  <div
    class="sc-card"
    :data-padding="padding"
    :style="[cardStyle, style]"
    @mouseenter="hover = interactive"
    @mouseleave="hover = false"
  >
    <div v-if="title || $slots.actions" class="sc-card__header" :style="headerStyle">
      <div class="sc-card__title-wrap">
        <h3 v-if="title" class="sc-card__title">{{ title }}</h3>
        <p v-if="subtitle" class="sc-card__subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="sc-card__actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="sc-card__body" :style="[bodyPaddingStyle, bodyStyle]">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  padding: { type: String, default: "md" },
  interactive: { type: Boolean, default: false },
  style: { type: Object, default: () => ({}) },
  bodyStyle: { type: Object, default: () => ({}) },
});

const hover = ref(false);
const pads = { none: 0, sm: "var(--space-4)", md: "var(--space-5)", lg: "var(--space-6)" };
const paddingValue = computed(() => pads[props.padding] ?? pads.md);

const cardStyle = computed(() => ({
  boxShadow: hover.value ? "var(--shadow-md)" : "var(--shadow-sm)",
  transform: hover.value ? "translateY(-2px)" : "none",
  cursor: props.interactive ? "pointer" : "default",
}));

const headerStyle = computed(() => {
  const value = paddingValue.value === 0 ? "var(--space-5)" : paddingValue.value;
  return { padding: value };
});

const bodyPaddingStyle = computed(() => ({ padding: paddingValue.value }));
</script>

<style scoped>
.sc-card {
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  transition: box-shadow var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out);
  overflow: hidden;
}

.sc-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.sc-card__title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sc-card__title {
  font: var(--font-card-title);
  color: var(--text-strong);
  letter-spacing: var(--tracking-snug);
}

.sc-card__subtitle {
  font: var(--font-caption);
  color: var(--text-muted);
}

.sc-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 560px) {
  .sc-card__header { padding: 14px !important; gap: 8px; }
  .sc-card:not([data-padding="none"]) .sc-card__body { padding: 14px !important; }
  .sc-card__title { font-size: 14px; line-height: 1.3; }
  .sc-card__subtitle { line-height: 1.35; }
  .sc-card__actions { max-width: 45%; overflow-x: auto; }
}
</style>
