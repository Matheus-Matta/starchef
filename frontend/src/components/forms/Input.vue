<template>
  <div class="sc-input" :style="style">
    <label v-if="label" :for="inputId" class="sc-input__label">
      {{ label }}<span v-if="required" class="sc-input__required">*</span>
    </label>
    <div class="sc-input__control" :style="controlStyle">
      <span v-if="$slots.icon" class="sc-input__affix">
        <slot name="icon" />
      </span>
      <input
        :id="inputId"
        :type="type"
        :disabled="disabled"
        :required="required"
        :placeholder="placeholder"
        :value="modelValue"
        :style="inputStyle"
        @input="$emit('update:modelValue', $event.target.value)"
        @focus="focused = true"
        @blur="focused = false"
      />
      <span v-if="$slots.trailing" class="sc-input__affix">
        <slot name="trailing" />
      </span>
    </div>
    <span v-if="error" class="sc-input__error">{{ error }}</span>
    <span v-else-if="hint" class="sc-input__hint">{{ hint }}</span>
  </div>
</template>

<script setup>
import { computed, getCurrentInstance, ref } from "vue";

const props = defineProps({
  modelValue: { type: [String, Number], default: "" },
  label: { type: String, default: "" },
  hint: { type: String, default: "" },
  error: { type: String, default: "" },
  size: { type: String, default: "md" },
  type: { type: String, default: "text" },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  id: { type: String, default: "" },
  placeholder: { type: String, default: "" },
  style: { type: Object, default: () => ({}) },
});

defineEmits(["update:modelValue"]);

const uid = getCurrentInstance().uid;
const focused = ref(false);
const inputId = computed(() => props.id || `sc-input-${uid}`);

const sizes = {
  sm: { h: "var(--control-sm)", px: 10, font: "var(--text-sm)" },
  md: { h: "var(--control-md)", px: 12, font: "var(--text-base)" },
  lg: { h: "var(--control-lg)", px: 14, font: "var(--text-md)" },
};

const sizeStyle = computed(() => sizes[props.size] || sizes.md);
const borderColor = computed(() => {
  if (props.error) return "var(--danger)";
  return focused.value ? "var(--ring)" : "var(--border-strong)";
});

const controlStyle = computed(() => ({
  height: sizeStyle.value.h,
  padding: `0 ${sizeStyle.value.px}px`,
  background: props.disabled ? "var(--surface-sunken)" : "var(--surface-card)",
  border: `1px solid ${borderColor.value}`,
  boxShadow: focused.value ? "0 0 0 3px color-mix(in srgb, var(--ring) 22%, transparent)" : "var(--shadow-xs)",
  opacity: props.disabled ? 0.6 : 1,
}));

const inputStyle = computed(() => ({
  font: `var(--weight-medium) ${sizeStyle.value.font}/1 var(--font-sans)`,
}));
</script>

<style scoped>
.sc-input {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sc-input__label {
  font: var(--font-label);
  color: var(--text-body);
}

.sc-input__required {
  color: var(--danger);
  margin-left: 3px;
}

.sc-input__control {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: var(--radius-md);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}

.sc-input__affix {
  display: inline-flex;
  color: var(--text-subtle);
  font-size: 17px;
}

.sc-input input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-strong);
}

.sc-input__error {
  font: var(--font-caption);
  color: var(--danger-text);
}

.sc-input__hint {
  font: var(--font-caption);
  color: var(--text-muted);
}
</style>
