<template>
  <div class="sc-tabs" :style="[tabsStyle, style]">
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      :style="tabStyle(item.value)"
      @click="select(item.value)"
    >
      <span v-if="item.icon" class="sc-tabs__icon">
        <AppIcon :name="item.icon" :size="15" />
      </span>
      {{ item.label }}
      <span v-if="item.count != null" class="sc-tabs__count" :style="countStyle(item.value)">
        {{ item.count }}
      </span>
    </button>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import AppIcon from "../AppIcon.vue";

const props = defineProps({
  items: { type: Array, default: () => [] },
  modelValue: { type: [String, Number], default: undefined },
  size: { type: String, default: "md" },
  fill: { type: Boolean, default: false },
  style: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:modelValue", "change"]);
const internal = ref(props.items[0]?.value);

watch(
  () => props.items,
  (items) => {
    if (internal.value === undefined) internal.value = items[0]?.value;
  },
);

const active = computed(() => (props.modelValue !== undefined ? props.modelValue : internal.value));
const isSmall = computed(() => props.size === "sm");

const tabsStyle = computed(() => ({
  width: props.fill ? "100%" : "auto",
}));

function select(value) {
  internal.value = value;
  emit("update:modelValue", value);
  emit("change", value);
}

function tabStyle(value) {
  const on = value === active.value;
  return {
    flex: props.fill ? 1 : "none",
    height: isSmall.value ? "28px" : "34px",
    background: on ? "var(--surface-card)" : "transparent",
    color: on ? "var(--text-strong)" : "var(--text-muted)",
    boxShadow: on ? "var(--shadow-xs)" : "none",
    font: `var(--weight-semibold) ${isSmall.value ? "var(--text-sm)" : "var(--text-base)"}/1 var(--font-sans)`,
  };
}

function countStyle(value) {
  const on = value === active.value;
  return {
    background: on ? "var(--brand-subtle)" : "var(--surface-active)",
    color: on ? "var(--text-brand)" : "var(--text-muted)",
  };
}
</script>

<style scoped>
.sc-tabs {
  display: inline-flex;
  padding: 4px;
  gap: 2px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.sc-tabs button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 14px;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: box-shadow var(--dur-fast);
  white-space: nowrap;
}

.sc-tabs__icon {
  display: inline-flex;
}

.sc-tabs__count {
  margin-left: 2px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  font: var(--weight-bold) var(--text-2xs) / 1 var(--font-sans);
}
</style>
