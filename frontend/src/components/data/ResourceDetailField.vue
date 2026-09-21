<template>
  <div class="detail-field">
    <span class="detail-field__label">{{ field.label }}</span>
    <span v-if="field.type === 'status'" class="status-chip" :data-status="field._value">
      {{ mapLabel(field._value, field.map) }}
    </span>
    <Tag
      v-else-if="field.type === 'boolean'"
      :value="field._value ? 'Ativo' : 'Inativo'"
      :severity="field._value ? 'success' : 'danger'"
      rounded
    />
    <RouterLink
      v-else-if="field.type === 'order-link' && record[field.idKey]"
      class="detail-field__link"
      :to="{ name: 'pedidos--view', params: { id: record[field.idKey] } }"
    >
      Pedido #{{ mapLabel(field._value) }} <i class="pi pi-external-link" />
    </RouterLink>
    <span v-else-if="field.type === 'order-link'" class="detail-field__value">-</span>
    <strong v-else-if="field.type === 'money'" class="detail-field__money">
      {{ formatMoney(field._value) }}
    </strong>
    <span v-else-if="field.type === 'date'" class="detail-field__value">
      {{ formatDateTime(field._value, { withYear: true }) }}
    </span>
    <span v-else class="detail-field__value">{{ mapLabel(field._value, field.map) }}</span>
  </div>
</template>

<script setup>
import Tag from "primevue/tag";

import { formatDateTime, formatMoney, mapLabel } from "../../utils/format";

defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
});
</script>

<style scoped>
.detail-field { display: flex; flex-direction: column; gap: 7px; padding: 14px 18px; background: var(--surface-card); }
.detail-field__label { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps); }
.detail-field__value { color: var(--text-strong); font: var(--weight-semibold) 13.5px/1.4 var(--font-sans); word-break: break-word; }
.detail-field__money { color: var(--success-text); font: var(--weight-extra) 14.5px/1 var(--font-sans); }
.detail-field__link {
  display: inline-flex; align-items: center; gap: 6px; width: fit-content;
  color: var(--text-brand); font: var(--weight-bold) 13.5px/1.4 var(--font-sans);
  text-decoration: none;
}
.detail-field__link:hover { text-decoration: underline; text-underline-offset: 3px; }
.detail-field__link .pi { font-size: 11px; }
.status-chip {
  display: inline-flex; align-items: center; width: fit-content;
  padding: 3px 9px; border-radius: 99px; border: 1px solid transparent;
  font: var(--weight-extra) 11px/1 var(--font-sans); white-space: nowrap; color: #fff; background: #475569;
}
.status-chip[data-status="open"]             { background: #2563eb; }
.status-chip[data-status="sent_to_kitchen"]  { background: #7c3aed; }
.status-chip[data-status="preparing"]        { background: #4338ca; }
.status-chip[data-status="partially_ready"]  { background: #0891b2; }
.status-chip[data-status="ready"]            { background: #059669; }
.status-chip[data-status="delivered"]        { background: #16a34a; }
.status-chip[data-status="awaiting_payment"] { background: #d97706; }
.status-chip[data-status="paid"]             { background: #047857; }
.status-chip[data-status="cancelled"]        { background: #b91c1c; }
.status-chip[data-status="refunded"]         { background: #be185d; }
.status-chip[data-status="free"]             { background: #047857; }
.status-chip[data-status="occupied"]         { background: #b91c1c; }
.status-chip[data-status="reserved"]         { background: #1d4ed8; }
.status-chip[data-status="cleaning"]         { background: #b45309; }
.status-chip[data-status="closed"]           { background: #475569; }
.status-chip[data-status="issued"]           { background: #047857; }
.status-chip[data-status="draft"]            { background: #64748b; }
.status-chip[data-status="error"]            { background: #b91c1c; }
.status-chip[data-status="in"]               { background: #047857; }
.status-chip[data-status="out"]              { background: #b91c1c; }
.status-chip[data-status="adjustment"]       { background: #b45309; }
.status-chip[data-status="sale"]             { background: #7c3aed; }
.status-chip[data-status="inventory"]        { background: #475569; }
.status-chip[data-status="admin"]            { background: #b91c1c; }
.status-chip[data-status="owner"]            { background: #7c3aed; }
.status-chip[data-status="manager"]          { background: #1d4ed8; }
.status-chip[data-status="waiter"]           { background: #0891b2; }
.status-chip[data-status="kitchen"]          { background: #d97706; }
.status-chip[data-status="cashier"]          { background: #059669; }
.status-chip[data-status="driver"]           { background: #475569; }
:deep(.p-tag) { border: 1px solid transparent; font: var(--weight-extra) 11px/1 var(--font-sans); }
:deep(.p-tag.p-tag-success) { background: #047857; border-color: #065f46; color: #fff; }
:deep(.p-tag.p-tag-danger) { background: #b91c1c; border-color: #991b1b; color: #fff; }
</style>
