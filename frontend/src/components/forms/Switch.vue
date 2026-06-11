<template>
  <label v-if="label" class="sc-switch-label" :for="switchId">
    <button v-bind="buttonAttrs" />
    <span>{{ label }}</span>
  </label>
  <button v-else v-bind="buttonAttrs" />
</template>

<script setup>
import { computed, getCurrentInstance } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  size: { type: String, default: "md" },
  label: { type: String, default: "" },
  id: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);

const uid = getCurrentInstance().uid;
const switchId = computed(() => props.id || `sc-switch-${uid}`);
const dims = computed(() => (props.size === "sm" ? { w: 34, h: 20, k: 14 } : { w: 44, h: 26, k: 20 }));

const controlStyle = computed(() => ({
  width: `${dims.value.w}px`,
  height: `${dims.value.h}px`,
  "--knob-left": props.modelValue ? `${dims.value.w - dims.value.k - 3}px` : "3px",
  "--knob-size": `${dims.value.k}px`,
  background: props.modelValue ? "var(--brand)" : "var(--border-strong)",
  opacity: props.disabled ? 0.55 : 1,
  cursor: props.disabled ? "not-allowed" : "pointer",
}));

const buttonAttrs = computed(() => ({
  id: switchId.value,
  type: "button",
  role: "switch",
  "aria-checked": String(props.modelValue),
  disabled: props.disabled,
  class: "sc-switch",
  style: controlStyle.value,
  onClick: () => {
    if (!props.disabled) emit("update:modelValue", !props.modelValue);
  },
}));
</script>

<style scoped>
.sc-switch-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font: var(--font-body);
  color: var(--text-body);
}

.sc-switch {
  position: relative;
  flex-shrink: 0;
  padding: 0;
  border-radius: var(--radius-pill);
  border: 1px solid transparent;
  transition: background var(--dur-base) var(--ease-out);
}

.sc-switch::after {
  content: "";
  position: absolute;
  top: 50%;
  left: var(--knob-left);
  width: var(--knob-size);
  height: var(--knob-size);
  transform: translateY(-50%);
  border-radius: 50%;
  background: #fff;
  box-shadow: var(--shadow-sm);
  transition: left var(--dur-base) var(--ease-out);
}
</style>
