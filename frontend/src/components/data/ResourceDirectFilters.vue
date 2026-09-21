<template>
  <label
    v-for="field in fields"
    :key="field.name"
    class="rpro__inline-filter"
    :class="{ 'rpro__inline-filter--compact': field.compact }"
  >
    <span>{{ field.label }}</span>
    <select :aria-label="field.label" :value="values[field.name] || ''" @change="change(field.name, $event.target.value)">
      <option value="">{{ field.compact ? `${field.label}: Todos` : "Todos" }}</option>
      <option v-for="option in field.options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </label>
</template>

<script setup>
defineProps({
  fields: { type: Array, default: () => [] },
  values: { type: Object, required: true },
});

const emit = defineEmits(["change"]);
const change = (name, value) => emit("change", { name, value });
</script>

<style scoped>
.rpro__inline-filter { display: flex; flex-direction: column; gap: 3px; min-width: 148px; }
.rpro__inline-filter--compact > span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.rpro__inline-filter span {
  color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans);
  text-transform: uppercase; letter-spacing: var(--tracking-caps);
}
.rpro__inline-filter select {
  height: var(--control-h); padding: 0 28px 0 10px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-medium) 13px/1 var(--font-sans);
}
@media (max-width: 900px) { .rpro__inline-filter { width: 100%; flex: none; } }
</style>
