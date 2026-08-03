<template>
  <DataTable
    :value="rows"
    paginator
    :rows="10"
    :rows-per-page-options="[10, 20, 50]"
    paginator-template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown"
    responsive-layout="scroll"
    striped-rows
    class="report-data-table"
  >
    <Column
      v-for="column in columns"
      :key="column.key"
      :field="column.key"
      :header="column.label"
      :sortable="column.sortable !== false"
      :body-style="{ textAlign: column.align || 'left' }"
      :header-style="{ textAlign: column.align || 'left' }"
    >
      <template #body="{ data }">
        {{ formatValue(data[column.key], column) }}
      </template>
    </Column>
    <template #empty>
      <div class="report-data-table__empty">Sem dados no período selecionado.</div>
    </template>
  </DataTable>
</template>

<script setup>
import Column from "primevue/column";
import DataTable from "primevue/datatable";

defineProps({
  rows: { type: Array, required: true },
  columns: { type: Array, required: true },
});

function formatValue(value, column) {
  if (column.type === "money") {
    return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  if (column.type === "decimal") {
    return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  }
  return value ?? "—";
}
</script>

<style scoped>
.report-data-table__empty {
  padding: 28px;
  color: var(--text-muted);
  text-align: center;
}

.report-data-table :deep(.p-datatable-thead > tr > th),
.report-data-table :deep(.p-datatable-tbody > tr > td) {
  padding: 12px 16px;
}

@media (max-width: 720px) {
  .report-data-table :deep(.p-datatable-wrapper) { overscroll-behavior-x: contain; }
  .report-data-table :deep(table) { min-width: 620px; }
  .report-data-table :deep(.p-datatable-thead > tr > th),
  .report-data-table :deep(.p-datatable-tbody > tr > td) {
    padding: 10px 12px;
    font-size: 12px;
    white-space: nowrap;
  }
  .report-data-table :deep(.p-paginator) {
    justify-content: center;
    gap: 2px;
    padding: 8px 6px;
    flex-wrap: nowrap;
    overflow-x: auto;
  }
  .report-data-table :deep(.p-paginator-page),
  .report-data-table :deep(.p-paginator-first),
  .report-data-table :deep(.p-paginator-prev),
  .report-data-table :deep(.p-paginator-next),
  .report-data-table :deep(.p-paginator-last) {
    min-width: 32px;
    width: 32px;
    height: 32px;
  }
  .report-data-table__empty { padding: 22px 12px; }
}
</style>
