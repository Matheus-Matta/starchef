<template>
  <div class="resource-view" :class="{ 'resource-view--cards': isCardResource, 'resource-view--fill': showTable }">
    <Toolbar class="resource-toolbar">
      <template #start>
        <IconField icon-position="left" class="resource-toolbar__search">
          <InputIcon class="pi pi-search" />
          <InputText v-model="search" :placeholder="`Buscar em ${title.toLowerCase()}...`" @keyup.enter="loadRows" />
        </IconField>
      </template>

      <template #end>
        <div class="resource-toolbar__actions">
          <Dropdown
            v-if="isMenuCatalog"
            v-model="activeFilter"
            class="resource-filter"
            :options="activeOptions"
            option-label="label"
            option-value="value"
            @change="loadRows"
          />
          <Dropdown
            v-if="isMenuCatalog"
            v-model="typeFilter"
            class="resource-filter"
            :options="typeOptions"
            option-label="label"
            option-value="value"
            @change="loadRows"
          />
          <Dropdown
            v-if="isMenuCatalog"
            v-model="sectorFilter"
            class="resource-filter"
            :options="sectorOptions"
            option-label="label"
            option-value="value"
            @change="loadRows"
          />
          <SelectButton
            v-if="isCardResource"
            v-model="viewMode"
            class="view-mode"
            :options="viewModeOptions"
            option-label="label"
            option-value="value"
            :allow-empty="false"
          />
          <Button v-if="formEnabled" icon="pi pi-plus" label="Novo" @click="goToCreate" />
        </div>
      </template>
    </Toolbar>

    <div v-if="error" class="resource-error">
      <i class="pi pi-exclamation-triangle" />
      {{ error }}
    </div>

    <template v-if="isCardResource && viewMode === 'grid'">
      <div v-if="loading" class="table-grid">
        <div v-for="index in 8" :key="index" class="table-card table-card--loading">
          <Skeleton height="150px" border-radius="14px" />
          <Skeleton width="70%" height="18px" />
          <Skeleton width="100%" height="38px" />
          <Skeleton width="44%" height="28px" />
        </div>
      </div>

      <div v-else-if="rows.length && isTableCards" class="table-grid">
        <article
          v-for="table in rows"
          :key="table.id"
          class="table-card"
          :class="`table-card--${table.status || 'free'}`"
          tabindex="0"
          @click="openDetail(table)"
          @keyup.enter="openDetail(table)"
        >
          <div class="table-card__top">
            <strong class="table-card__number">{{ table.number || "-" }}</strong>
            <span class="table-card__status">{{ tableStatusLabel(table.status) }}</span>
          </div>
          <div class="table-card__info">
            <span>{{ table.capacity || 0 }} lugares</span>
            <span>{{ table.sector_name || "Sem setor" }}</span>
          </div>
        </article>
      </div>

      <div v-else class="resource-empty">
        <i class="pi pi-search" />
        <strong>Nenhum registro encontrado</strong>
        <span>Ajuste a busca ou atualize para ver outros resultados.</span>
      </div>
    </template>

    <section v-else class="resource-panel">
      <DataTable
        :value="rows"
        data-key="id"
        class="resource-datatable"
        :loading="loading"
        :row-hover="true"
        scrollable
        scroll-height="flex"
        removable-sort
        :sort-field="sortField"
        :sort-order="sortOrder"
        @sort="onSort"
        @row-click="openDetail($event.data)"
      >
        <Column
          v-for="column in columns"
          :key="column.key"
          :field="column.key"
          :header="column.label"
          :sortable="column.sortable !== false"
          :body-style="columnBodyStyle(column)"
          :header-class="column.align === 'right' ? 'dt-col-right' : undefined"
        >
          <template #body="{ data }">
            <span v-if="column.type === 'status'" class="status-chip" :data-status="value(data, column)">{{ label(value(data, column), column.map) }}</span>
            <span v-else-if="column.type === 'money'" class="num strong">{{ money(value(data, column)) }}</span>
            <span v-else-if="column.type === 'date'" class="num muted">{{ dateTime(value(data, column)) }}</span>
            <Tag
              v-else-if="column.type === 'boolean'"
              :value="value(data, column) ? 'Ativo' : 'Inativo'"
              :severity="value(data, column) ? 'success' : 'danger'"
              rounded
            />
            <span v-else class="cell-text">{{ label(value(data, column), column.map) }}</span>
          </template>
        </Column>

        <Column header="Ações" :sortable="false" :body-style="{ textAlign: 'right', width: '128px' }" :style="{ width: '128px' }">
          <template #body="{ data }">
            <div class="resource-row-actions" @click.stop>
              <Button icon="pi pi-eye" text rounded aria-label="Ver detalhe" @click="openDetail(data)" />
              <Button v-if="formEnabled" icon="pi pi-pencil" text rounded aria-label="Editar" @click="goToEdit(data)" />
              <Button v-if="formEnabled" icon="pi pi-trash" text rounded severity="danger" aria-label="Excluir" @click="confirmDelete(data)" />
            </div>
          </template>
        </Column>

        <template #empty>
          <div class="resource-empty resource-empty--table">
            <i class="pi pi-inbox" />
            <strong>Nenhum registro encontrado</strong>
            <span>Ajuste a busca ou os filtros para ver outros resultados.</span>
          </div>
        </template>
      </DataTable>

      <Paginator
        v-if="total > 0"
        class="resource-paginator"
        :rows="rowsPerPage"
        :total-records="total"
        :first="firstRecord"
        :rows-per-page-options="[10, 25, 50, 100]"
        template="CurrentPageReport FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown"
        current-page-report-template="{first}–{last} de {totalRecords}"
        @page="onPage"
      />
    </section>

    <div v-if="isCardResource && viewMode === 'grid'" class="resource-footer">
      <Button label="Anterior" icon="pi pi-chevron-left" severity="secondary" outlined :disabled="!previousUrl || loading" @click="loadUrl(previousUrl)" />
      <span>Pagina {{ page }}</span>
      <Button label="Proxima" icon="pi pi-chevron-right" icon-pos="right" severity="secondary" outlined :disabled="!nextUrl || loading" @click="loadUrl(nextUrl)" />
    </div>
  </div>
</template>

<script setup>
/**
 * View (MVP) da listagem de um recurso.
 * Toda a logica de dados vem do presenter `useResourceList`; aqui so ficam o
 * template, os filtros especificos da tela e os formatadores de exibicao.
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Column from "primevue/column";
import IconField from "primevue/iconfield";
import InputIcon from "primevue/inputicon";
import DataTable from "primevue/datatable";
import Dropdown from "primevue/dropdown";
import InputText from "primevue/inputtext";
import SelectButton from "primevue/selectbutton";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import Toolbar from "primevue/toolbar";
import Paginator from "primevue/paginator";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { useResourceList } from "../composables/useResourceList";
import { ResourceService } from "../services/ResourceService";
import { ACTIVE_FILTER_OPTIONS, PRODUCT_TYPE_FILTER_OPTIONS, SECTOR_FILTER_OPTIONS, TABLE_STATUS_LABELS } from "../config/enums";
import { formatDateTime, formatMoney, mapLabel } from "../utils/format";
import { resolveColumnValue } from "../utils/object";
import { normalizeApiError } from "../utils/apiError";

const route = useRoute();
const router = useRouter();

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "Dados carregados do backend." },
  endpoint: { type: String, required: true },
  columns: { type: Array, required: true },
  defaultParams: { type: Object, default: () => ({}) },
  formEnabled: { type: Boolean, default: false },
  globalScope: { type: Boolean, default: false },
});

// Filtros exclusivos do cardapio (produtos). Ativos/tipo/setor.
const activeFilter = ref("all");
const typeFilter = ref("all");
const sectorFilter = ref("all");
const viewMode = ref("grid");

const isMenuCatalog = computed(() => props.endpoint.includes("/menu/products"));
// Só as MESAS usam a grade de cards. Endpoints como /tables/sectors/ (Setores)
// NÃO são mesas — devem usar a DataTable padrão.
const isTableCards = computed(() => /\/tables\/?$/.test(props.endpoint));
const isCardResource = computed(() => isTableCards.value);
// Mostra a DataTable (não os cards) — usada para preencher a altura da página.
const showTable = computed(() => !(isCardResource.value && viewMode.value === "grid"));

/** Traduz os filtros da tela em query params — so aplica no cardapio. */
function buildFilterParams() {
  if (!isMenuCatalog.value) return {};
  const params = {};
  if (activeFilter.value !== "all") params.is_active = activeFilter.value;
  if (typeFilter.value !== "all") params.product_type = typeFilter.value;
  if (sectorFilter.value !== "all") params.production_sector = sectorFilter.value;
  return params;
}

// Presenter: estado + busca + paginacao. A View so consome.
const service = new ResourceService({ endpoint: props.endpoint, globalScope: props.globalScope });
const {
  rows, total, page, rowsPerPage, ordering, nextUrl, previousUrl, loading, error, search,
  load, reload, goToPage, setPageSize, setSort, loadUrl,
} = useResourceList({
  service,
  defaultParams: props.defaultParams,
  buildParams: buildFilterParams,
});
// Busca/filtros voltam à primeira página; a carga inicial também.
const loadRows = reload;

const confirm = useConfirm();
const toast = useToast();

/* ── Ordenação server-side (DataTable → parâmetro `ordering`) ─────────── */
const sortField = computed(() => (ordering.value ? ordering.value.replace(/^-/, "") : null));
const sortOrder = computed(() => (ordering.value ? (ordering.value.startsWith("-") ? -1 : 1) : null));
function onSort(event) {
  setSort(event.sortField, event.sortOrder);
}

/* ── Paginação server-side (Paginator) ───────────────────────────────── */
const firstRecord = computed(() => (page.value - 1) * rowsPerPage.value);
function onPage(event) {
  if (event.rows !== rowsPerPage.value) setPageSize(event.rows);
  else goToPage(event.page + 1);
}

/* ── Ações de linha: ver / editar / excluir (com confirmação) ────────── */
function goToEdit(row) {
  if (!row?.id) return;
  router.push({ name: `${route.name}--edit`, params: { id: row.id } });
}
function confirmDelete(row) {
  if (!row?.id) return;
  confirm.require({
    header: "Excluir registro?",
    message: `Tem certeza que deseja excluir "${rowLabel(row)}"? Esta ação não pode ser desfeita.`,
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Excluir",
    rejectLabel: "Cancelar",
    acceptClass: "p-button-danger",
    accept: () => remove(row),
  });
}
async function remove(row) {
  try {
    await service.remove(row.id);
    toast.add({ severity: "success", summary: "Registro excluído", life: 2500 });
    // Se a página ficou vazia após excluir, recua uma página.
    if (rows.value.length === 1 && page.value > 1) goToPage(page.value - 1);
    else load();
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível excluir", detail: normalizeApiError(err).message, life: 5000 });
  }
}
function rowLabel(row) {
  return row.name || row.trade_name || row.username || row.number || `#${row.id}`;
}

// Opcoes de filtro/visualizacao (centralizadas em config/enums.js).
const activeOptions = ACTIVE_FILTER_OPTIONS;
const typeOptions = PRODUCT_TYPE_FILTER_OPTIONS;
const sectorOptions = SECTOR_FILTER_OPTIONS;
const viewModeOptions = [
  { label: "Cards", value: "grid" },
  { label: "Tabela", value: "table" },
];


/* Clique na linha/card → pagina de detalhe (view), substitui o antigo drawer. */
function openDetail(row) {
  if (!row?.id) return;
  router.push({ name: `${route.name}--view`, params: { id: row.id } });
}
function goToCreate() {
  router.push({ name: `${route.name}--create` });
}

/* ── Helpers de exibicao (delegam aos utils compartilhados) ──────────── */
const value = resolveColumnValue;
const label = mapLabel;
const money = formatMoney;
const dateTime = formatDateTime;

function tableStatusLabel(status) {
  return TABLE_STATUS_LABELS[status] || "Status";
}
function columnBodyStyle(column) {
  return { textAlign: column.align === "right" ? "right" : "left", whiteSpace: "nowrap" };
}

onMounted(loadRows);
</script>

<style scoped>
.resource-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Modo tabela: a lista preenche a altura restante da página e o corpo (tbody)
   rola internamente, mantendo cabeçalho e paginação fixos. */
.resource-view--fill {
  height: 100%;
  min-height: 0;
  gap: 0; /* header (toolbar) e tabela unidos em um bloco só */
}
/* Mantém respiro apenas para o hero/erro quando existirem */
.resource-view--fill .table-overview,
.resource-view--fill .resource-error {
  margin-bottom: 16px;
}
/* Toolbar vira o topo do card: cantos inferiores retos, sem raio embaixo */
.resource-view--fill .resource-toolbar {
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}
/* Painel da tabela cola no toolbar: sem borda/raio no topo (a borda inferior do
   toolbar vira o separador), formando um único card contínuo */
.resource-view--fill .resource-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: none;
  border-top-left-radius: 0;
  border-top-right-radius: 0;
}
.resource-view--fill :deep(.resource-datatable) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.resource-view--fill :deep(.resource-datatable .p-datatable-wrapper) {
  flex: 1;
  min-height: 0;
}

.menu-hero {
  min-height: 188px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.72fr);
  gap: 18px;
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.1), transparent 46%),
    linear-gradient(45deg, rgba(22, 163, 74, 0.1), transparent 50%),
    var(--surface-card);
  overflow: hidden;
}

.menu-hero__copy {
  max-width: 640px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
}

.menu-hero__eyebrow {
  width: fit-content;
  padding: 6px 10px;
  border-radius: var(--radius-pill);
  background: var(--surface-card);
  color: var(--info-text);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.menu-hero h2 {
  max-width: 620px;
  font: var(--weight-extra) 32px/1.08 var(--font-sans);
  color: var(--text-strong);
}

.menu-hero p {
  max-width: 520px;
  color: var(--text-muted);
  font: var(--weight-medium) 14px/1.6 var(--font-sans);
}

.menu-hero__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  align-content: end;
}

.menu-metric {
  min-height: 104px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 7px;
  padding: 16px;
  border: 1px solid rgba(37, 99, 235, 0.18);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow-sm);
}

[data-theme="dark"] .menu-metric {
  background: rgba(24, 24, 27, 0.74);
}

.menu-metric span {
  color: var(--text-strong);
  font: var(--weight-extra) 24px/1 var(--font-sans);
}

.menu-metric small {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1.3 var(--font-sans);
}

.menu-metric--green { border-color: rgba(22, 163, 74, 0.24); }
.menu-metric--blue { border-color: rgba(37, 99, 235, 0.24); }

.table-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.82fr);
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
}

.table-overview__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}

.table-overview__copy span {
  color: var(--info-text);
  font: var(--weight-extra) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
}

.table-overview__copy h2 {
  color: var(--text-strong);
  font: var(--weight-extra) 22px/1.18 var(--font-sans);
}

.table-overview__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.table-overview__metrics div {
  min-height: 78px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.table-overview__metrics strong {
  color: var(--text-strong);
  font: var(--weight-extra) 22px/1 var(--font-sans);
}

.table-overview__metrics span {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1 var(--font-sans);
}

.resource-toolbar {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  padding: 10px;
  overflow: visible;
}

.resource-toolbar__search { width: min(420px, 46vw); }

.resource-toolbar__actions {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  justify-content: flex-end;
  gap: 8px;
}

.resource-filter { min-width: 148px; flex-shrink: 0; }

.resource-error {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 14px;
  color: var(--danger-text);
  background: var(--danger-subtle);
  border: 1px solid rgba(220, 38, 38, 0.16);
  border-radius: var(--radius-md);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

.table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

/* Card de mesa compacto: número, status, capacidade e setor — sem ícones */
.table-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-left: 4px solid #475569; /* cor por status na lateral */
  border-radius: var(--radius-md);
  background: var(--surface-card);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out), border-color var(--dur-base) var(--ease-out);
}

.table-card:hover,
.table-card:focus-visible {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.table-card--free { border-left-color: #047857; }
.table-card--occupied { border-left-color: #b91c1c; }
.table-card--reserved { border-left-color: #1d4ed8; }
.table-card--cleaning { border-left-color: #b45309; }

.table-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.table-card__number { color: var(--text-strong); font: var(--weight-extra) 26px/1 var(--font-sans); }
.table-card__status {
  flex-shrink: 0;
  color: var(--text-muted);
  font: var(--weight-bold) 10.5px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.table-card--free .table-card__status { color: var(--success-text); }
.table-card--occupied .table-card__status { color: var(--danger-text); }

.table-card__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: var(--text-muted);
  font: var(--weight-semibold) 12px/1.3 var(--font-sans);
}
.table-card__info span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.resource-panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
}

.resource-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border-bottom: 1px solid var(--border-subtle);
}

.resource-panel__header h2 { color: var(--text-strong); font: var(--font-card-title); }
.resource-panel__header p { margin-top: 4px; color: var(--text-muted); font: var(--font-caption); }

.cell-text {
  max-width: 280px;
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}

.strong { color: var(--text-strong); font-weight: var(--weight-bold); }
.muted { color: var(--text-muted); }
.resource-row-arrow { color: var(--text-subtle); font-size: 12px; }

.resource-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  justify-content: flex-end;
}
.resource-row-actions :deep(.p-button.p-button-icon-only) {
  width: 30px;
  height: 30px;
}

.resource-paginator {
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-card);
}

.resource-empty {
  min-height: 260px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-muted);
  text-align: center;
}

.resource-empty--table { min-height: 180px; }
.resource-empty i { color: var(--text-subtle); font-size: 28px; }
.resource-empty strong { color: var(--text-strong); font: var(--weight-bold) 15px/1.2 var(--font-sans); }
.resource-empty span { font: var(--weight-medium) 13px/1.4 var(--font-sans); }

.resource-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.resource-footer span { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }

:deep(.p-toolbar) { gap: 10px; overflow: visible; flex-wrap: nowrap; }
:deep(.p-toolbar-group-start) { min-width: 0; flex: 1 1 auto; }
:deep(.p-toolbar-group-end) { min-width: 0; flex: 0 0 auto; }

:deep(.p-inputtext),
:deep(.p-dropdown),
:deep(.p-selectbutton .p-button),
:deep(.p-button) { font-family: var(--font-sans); }

:deep(.p-inputtext) { width: 100%; height: var(--control-h); }
:deep(.p-dropdown) { height: var(--control-h); align-items: center; }
:deep(.p-dropdown-label) {
  display: flex;
  align-items: center;
  padding: 0 0 0 10px;
  font: var(--weight-semibold) var(--control-font)/1 var(--font-sans);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
:deep(.p-dropdown-panel) { z-index: 9999 !important; }
:deep(.p-selectbutton .p-button) { height: var(--control-h); padding: 0 12px; }

:deep(.resource-datatable),
:deep(.resource-datatable .p-datatable-tbody),
:deep(.resource-datatable .p-datatable-thead) {
  font-family: var(--font-table);
}

:deep(.resource-datatable .p-datatable-thead > tr > th) {
  padding: 9px 12px;
  border-color: var(--border-subtle);
  color: var(--text-subtle);
  background: var(--surface-sunken);
  font: var(--weight-bold) 11.5px/1 var(--font-table);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

:deep(.resource-datatable .p-datatable-tbody > tr) {
  color: var(--text-body);
  background: var(--surface-card);
  cursor: pointer;
}

:deep(.resource-datatable .p-datatable-tbody > tr > td) {
  padding: 9px 12px;
  border-color: var(--border-subtle);
  font: var(--weight-regular) 14.5px/1.35 var(--font-table);
  color: var(--text-body);
}

:deep(.resource-datatable .p-datatable-tbody > tr:hover) { background: var(--surface-hover); }

/* Estado vazio (sem dados): sem borda e sem hover — é uma mensagem, não uma linha */
:deep(.resource-datatable .p-datatable-tbody > tr.p-datatable-emptymessage > td) {
  border: none;
  cursor: default;
}
:deep(.resource-datatable .p-datatable-tbody > tr.p-datatable-emptymessage:hover) {
  background: var(--surface-card);
}

/* Cabeçalho alinhado à direita quando o valor da coluna é à direita */
:deep(.resource-datatable .p-datatable-thead > tr > th.dt-col-right .p-column-header-content) {
  justify-content: flex-end;
}

/* Ícones de ordenação (asc/desc) menores e alinhados ao texto do cabeçalho */
:deep(.resource-datatable .p-sortable-column .p-sortable-column-icon) {
  width: 11px;
  height: 11px;
  font-size: 11px;
  margin-left: 4px;
}
:deep(.resource-datatable .p-sortable-column .p-sortable-column-badge) {
  min-width: 14px;
  height: 14px;
  line-height: 14px;
  font-size: 9px;
}

:deep(.p-tag) { border: 1px solid transparent; font: var(--weight-extra) 11px/1 var(--font-sans); }
:deep(.p-tag.p-tag-info) { background: #1d4ed8; border-color: #1e40af; color: #fff; }
:deep(.p-tag.p-tag-success) { background: #047857; border-color: #065f46; color: #fff; }
:deep(.p-tag.p-tag-warning) { background: #b45309; border-color: #92400e; color: #fff; }
:deep(.p-tag.p-tag-danger) { background: #b91c1c; border-color: #991b1b; color: #fff; }
:deep(.p-tag.p-tag-secondary) { background: #475569; border-color: #334155; color: #fff; }

/* ── Status chip: uma cor sólida por valor ─────────────────────────── */
.status-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 99px;
  border: 1px solid transparent;
  font: var(--weight-extra) 11px/1 var(--font-sans);
  white-space: nowrap;
  color: #fff;
  background: #475569;
}

.status-chip[data-status="open"]             { background: #2563eb; border-color: #1d4ed8; }
.status-chip[data-status="sent_to_kitchen"]  { background: #7c3aed; border-color: #6d28d9; }
.status-chip[data-status="preparing"]        { background: #4338ca; border-color: #3730a3; }
.status-chip[data-status="partially_ready"]  { background: #0891b2; border-color: #0e7490; }
.status-chip[data-status="ready"]            { background: #059669; border-color: #047857; }
.status-chip[data-status="delivered"]        { background: #16a34a; border-color: #15803d; }
.status-chip[data-status="awaiting_payment"] { background: #d97706; border-color: #b45309; }
.status-chip[data-status="paid"]             { background: #047857; border-color: #065f46; }
.status-chip[data-status="cancelled"]        { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="refunded"]         { background: #be185d; border-color: #9d174d; }

.status-chip[data-status="free"]      { background: #047857; border-color: #065f46; }
.status-chip[data-status="occupied"]  { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="reserved"]  { background: #1d4ed8; border-color: #1e40af; }
.status-chip[data-status="cleaning"]  { background: #b45309; border-color: #92400e; }

.status-chip[data-status="closed"]    { background: #475569; border-color: #334155; }
.status-chip[data-status="issued"]    { background: #047857; border-color: #065f46; }
.status-chip[data-status="draft"]     { background: #64748b; border-color: #475569; }
.status-chip[data-status="error"]     { background: #b91c1c; border-color: #991b1b; }

.status-chip[data-status="in"]          { background: #047857; border-color: #065f46; }
.status-chip[data-status="out"]         { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="adjustment"]  { background: #b45309; border-color: #92400e; }
.status-chip[data-status="sale"]        { background: #7c3aed; border-color: #6d28d9; }
.status-chip[data-status="inventory"]   { background: #475569; border-color: #334155; }

.status-chip[data-status="admin"]    { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="owner"]    { background: #7c3aed; border-color: #6d28d9; }
.status-chip[data-status="manager"]  { background: #1d4ed8; border-color: #1e40af; }
.status-chip[data-status="waiter"]   { background: #0891b2; border-color: #0e7490; }
.status-chip[data-status="kitchen"]  { background: #d97706; border-color: #b45309; }
.status-chip[data-status="cashier"]  { background: #059669; border-color: #047857; }
.status-chip[data-status="driver"]   { background: #475569; border-color: #334155; }

@media (max-width: 1180px) {
  .menu-hero { grid-template-columns: 1fr; }
  .table-overview { grid-template-columns: 1fr; }
  .menu-hero__metrics { align-content: stretch; }
}

@media (max-width: 860px) {
  :deep(.p-toolbar) { flex-wrap: wrap; }
  :deep(.p-toolbar-group-start) { flex: 1 1 100%; }
  :deep(.p-toolbar-group-end) { flex: 1 1 100%; }
  .resource-toolbar__search { width: 100%; }
  .resource-toolbar__actions { width: 100%; flex-wrap: wrap; justify-content: flex-start; }
  .resource-filter { flex: 1 1 140px; min-width: 0; }
  .resource-toolbar__actions :deep(.p-button),
  .view-mode { flex: 1 1 auto; }
}

@media (max-width: 640px) {
  .menu-hero { padding: 18px; }
  .menu-hero h2 { font-size: 25px; }
  .menu-hero__metrics,
  .table-overview__metrics { grid-template-columns: 1fr; }
  .resource-footer { justify-content: stretch; }
  .resource-footer :deep(.p-button) { flex: 1; }
}
</style>
