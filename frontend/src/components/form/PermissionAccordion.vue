<template>
  <div class="permission-accordion" :class="{ 'permission-accordion--disabled': disabled }">
    <div v-if="!groups.length" class="permission-accordion__empty">Nenhuma permissão disponível.</div>
    <details v-for="(group, index) in groups" v-else :key="group.label" class="permission-accordion__group" :open="index === 0">
      <summary>
        <span>{{ group.label }}</span>
        <small>{{ selectedCount(group) }} de {{ group.items.length }} ativas</small>
      </summary>
      <div class="permission-accordion__items">
        <label v-for="option in group.items" :key="option.value" class="permission-accordion__option">
          <input type="checkbox" :checked="selectedValues.has(option.value)" :disabled="disabled" @change="toggle(option.value, $event.target.checked)" />
          <span class="permission-accordion__check" aria-hidden="true"><i class="pi pi-check" /></span>
          <span class="permission-accordion__copy">
            <strong>{{ option.label }}</strong>
            <small v-if="option.description">{{ option.description }}</small>
          </span>
        </label>
      </div>
    </details>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  groups: { type: Array, default: () => [] },
  modelValue: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);
const selectedValues = computed(() => new Set(props.modelValue || []));

function selectedCount(group) {
  return group.items.filter((item) => selectedValues.value.has(item.value)).length;
}
function toggle(value, checked) {
  const next = new Set(props.modelValue || []);
  if (checked) next.add(value);
  else next.delete(value);
  emit("update:modelValue", [...next]);
}
</script>

<style scoped>
.permission-accordion { display: flex; flex-direction: column; gap: 9px; }
.permission-accordion__group { overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); }
.permission-accordion__group summary { min-height: 48px; padding: 0 15px; display: flex; align-items: center; gap: 10px; cursor: pointer; color: var(--text-strong); font: var(--weight-bold) 13.5px/1.2 var(--font-sans); background: var(--surface-sunken); }
.permission-accordion__group summary::marker { color: var(--text-muted); }
.permission-accordion__group summary span { flex: 1; }
.permission-accordion__group summary small { color: var(--text-muted); font: var(--weight-semibold) 11.5px/1 var(--font-sans); }
.permission-accordion__items { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; padding: 1px; background: var(--border-subtle); }
.permission-accordion__option { min-height: 58px; padding: 11px 13px; display: flex; align-items: flex-start; gap: 10px; cursor: pointer; background: var(--surface-card); }
.permission-accordion__option:hover { background: var(--nav-item-hover); }
.permission-accordion__option input { position: absolute; opacity: 0; pointer-events: none; }
.permission-accordion__check { width: 20px; height: 20px; flex: 0 0 20px; display: grid; place-items: center; border: 1px solid var(--border-strong); border-radius: 5px; color: transparent; background: var(--surface-card); }
.permission-accordion__option input:checked + .permission-accordion__check { color: #fff; border-color: var(--brand); background: var(--brand); }
.permission-accordion__option input:focus-visible + .permission-accordion__check { outline: 3px solid var(--brand-subtle); outline-offset: 2px; }
.permission-accordion__check i { font-size: 11px; font-weight: 800; }
.permission-accordion__copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.permission-accordion__copy strong { color: var(--text-strong); font: var(--weight-semibold) 13px/1.25 var(--font-sans); }
.permission-accordion__copy small, .permission-accordion__empty { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.35 var(--font-sans); }
.permission-accordion__empty { padding: 16px; border: 1px dashed var(--border); border-radius: var(--radius-md); }
.permission-accordion--disabled { opacity: .72; }
.permission-accordion--disabled .permission-accordion__option { cursor: default; }
@media (max-width: 760px) { .permission-accordion__items { grid-template-columns: 1fr; } }
</style>
