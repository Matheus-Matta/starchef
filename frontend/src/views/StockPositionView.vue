<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>Posição de estoque</h1>
        <p>
          O saldo de cada insumo, na unidade em que ele foi cadastrado. O número vem do livro de
          movimentos — entradas, saídas, baixas de venda e ajustes.
        </p>
      </div>
      <div class="stock-doc__head-actions">
        <Button label="Atualizar" icon="pi pi-refresh" text :loading="loading" @click="load" />
        <Button label="Novo insumo" icon="pi pi-plus" @click="newIngredient" />
      </div>
    </header>

    <div v-if="error" class="stock-doc__alert"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <div class="stock-kpis">
      <button
        v-for="kpi in kpis"
        :key="kpi.key"
        type="button"
        class="stock-kpi"
        :class="[`stock-kpi--${kpi.tone}`, { 'stock-kpi--on': kpi.filter !== null && situation === kpi.filter }]"
        @click="toggleKpi(kpi)"
      >
        <span class="stock-kpi__label">{{ kpi.label }}</span>
        <strong class="stock-kpi__value">{{ kpi.value }}</strong>
        <small>{{ kpi.hint }}</small>
      </button>
    </div>

    <section class="stock-card">
      <div class="stock-grid">
        <label class="stock-field stock-field--wide">
          <span>Buscar insumo</span>
          <InputText v-model="search" placeholder="Nome do insumo" fluid />
        </label>
        <label class="stock-field">
          <span>Local</span>
          <Select
            v-model="locationId"
            :options="locations"
            option-label="name"
            option-value="id"
            placeholder="Todos os locais"
            show-clear
            fluid
            @change="load"
          />
        </label>
        <label class="stock-field">
          <span>Situação</span>
          <Select
            v-model="situation"
            :options="situationOptions"
            option-label="label"
            option-value="value"
            fluid
          />
        </label>
      </div>
    </section>

    <section class="stock-card">
      <div v-if="loading"><Skeleton height="280px" /></div>

      <div v-else-if="!filteredRows.length" class="stock-empty">
        <i class="pi pi-inbox" />
        <p v-if="rows.length">Nenhum insumo com esse filtro.</p>
        <p v-else>Nenhum insumo cadastrado ainda. O estoque começa pelo cadastro do insumo.</p>
        <Button v-if="!rows.length" label="Cadastrar insumo" icon="pi pi-plus" size="small" @click="newIngredient" />
      </div>

      <DataTable
        v-else
        v-model:expanded-rows="expandedRows"
        :value="filteredRows"
        data-key="ingredient_id"
        size="small"
        class="stock-table"
        paginator
        :rows="25"
        :rows-per-page-options="[25, 50, 100]"
        removable-sort
      >
        <Column expander style="width: 42px" />
        <Column field="ingredient_name" header="Insumo" sortable>
          <template #body="{ data }">
            <div class="stock-pos__name">
              <strong>{{ data.ingredient_name }}</strong>
              <small v-if="!data.is_active">Inativo — ainda com saldo</small>
            </div>
          </template>
        </Column>
        <Column field="balance" header="Saldo" sortable>
          <template #body="{ data }">
            <span class="stock-pos__num" :class="{ 'stock-pos__num--bad': Number(data.balance) <= 0 }">
              {{ formatQuantity(data.balance) }} {{ data.unit }}
            </span>
          </template>
        </Column>
        <Column field="minimum_stock" header="Mínimo">
          <template #body="{ data }">
            <span class="stock-pos__num">
              {{ data.minimum_stock == null ? "—" : `${formatQuantity(data.minimum_stock)} ${data.unit}` }}
            </span>
          </template>
        </Column>
        <Column field="situation" header="Situação" sortable>
          <template #body="{ data }">
            <Tag :value="SITUATION_LABELS[data.situation]" :severity="SITUATION_SEVERITY[data.situation]" rounded />
          </template>
        </Column>
        <Column field="lot_count" header="Lotes">
          <template #body="{ data }">{{ data.lot_count || "—" }}</template>
        </Column>
        <Column field="next_expiry" header="Próx. validade" sortable>
          <template #body="{ data }">
            <span :class="{ 'stock-pos__num--bad': data.expired }">{{ formatDate(data.next_expiry) }}</span>
          </template>
        </Column>
        <Column field="average_cost" header="Custo médio">
          <template #body="{ data }">{{ formatMoney(data.average_cost) }}</template>
        </Column>
        <Column field="stock_value" header="Valor" sortable>
          <template #body="{ data }">{{ formatMoney(data.stock_value) }}</template>
        </Column>
        <Column style="width: 92px">
          <template #body="{ data }">
            <div class="stock-pos__actions">
              <Button
                icon="pi pi-pencil"
                text
                rounded
                size="small"
                title="Editar insumo"
                aria-label="Editar insumo"
                @click="editIngredient(data)"
              />
              <Button
                icon="pi pi-history"
                text
                rounded
                size="small"
                title="Ver movimentações"
                aria-label="Ver movimentações"
                @click="openMovements(data)"
              />
            </div>
          </template>
        </Column>

        <template #expansion="{ data }">
          <div class="stock-pos__expansion">
            <h3>Onde está este saldo</h3>
            <p v-if="!data.locations.length">Sem saldo em nenhum local.</p>
            <ul v-else>
              <li v-for="place in data.locations" :key="place.location_id">
                <span>{{ place.location_name }}</span>
                <strong>{{ formatQuantity(place.balance) }} {{ data.unit }}</strong>
              </li>
            </ul>
            <small v-if="data.last_movement_at">
              Última movimentação em {{ formatDateTime(data.last_movement_at) }}.
            </small>
          </div>
        </template>
      </DataTable>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import InputText from "primevue/inputtext";
import Select from "primevue/dropdown";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";

import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";
import { formatDateTime, formatMoney, formatQuantity } from "../utils/format";

const SITUATION_LABELS = { ok: "Em estoque", low: "Abaixo do mínimo", out: "Zerado" };
const SITUATION_SEVERITY = { ok: "success", low: "warning", out: "danger" };

const router = useRouter();

const loading = ref(true);
const error = ref("");
const rows = ref([]);
const totals = ref({});
const locations = ref([]);
const locationId = ref(null);
const search = ref("");
const situation = ref("");
const expandedRows = ref({});

const situationOptions = [
  { label: "Todas", value: "" },
  { label: "Em estoque", value: "ok" },
  { label: "Abaixo do mínimo", value: "low" },
  { label: "Zerado", value: "out" },
  { label: "Com lote vencido", value: "expired" },
];

const kpis = computed(() => [
  {
    key: "ingredients",
    label: "Insumos",
    value: totals.value.ingredients ?? 0,
    hint: "com posição nesta visão",
    tone: "neutral",
    filter: "",
  },
  {
    key: "low",
    label: "Abaixo do mínimo",
    value: totals.value.low ?? 0,
    hint: "precisam de compra",
    tone: "warning",
    filter: "low",
  },
  {
    key: "out",
    label: "Zerados",
    value: totals.value.out ?? 0,
    hint: "sem saldo disponível",
    tone: "danger",
    filter: "out",
  },
  {
    key: "value",
    label: "Valor em estoque",
    value: formatMoney(totals.value.stock_value),
    hint: "saldo x custo médio",
    tone: "neutral",
    filter: null,
  },
]);

/** Clicar no cartão liga/desliga o filtro que ele resume. */
function toggleKpi(kpi) {
  if (kpi.filter === null) return;
  situation.value = situation.value === kpi.filter ? "" : kpi.filter;
}

const filteredRows = computed(() => {
  const term = search.value.trim().toLowerCase();
  return rows.value.filter((row) => {
    if (term && !row.ingredient_name.toLowerCase().includes(term)) return false;
    if (!situation.value) return true;
    if (situation.value === "expired") return row.expired;
    return row.situation === situation.value;
  });
});

function formatDate(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).split("-");
  return day ? `${day}/${month}/${year}` : value;
}

function newIngredient() {
  router.push({ name: "ingredientes--create" });
}

function editIngredient(row) {
  router.push({ name: "ingredientes--edit", params: { id: row.ingredient_id } });
}

function openMovements(row) {
  router.push({ name: "estoque", query: { ingredient: row.ingredient_id } });
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const params = locationId.value ? { location: locationId.value } : {};
    const [positionsResponse, locationsResponse] = await Promise.all([
      api.get("/stock/positions/", { params }),
      // A lista de locais não muda com o filtro — só vale buscar na 1ª carga.
      locations.value.length
        ? Promise.resolve({ data: { results: locations.value } })
        : api.get("/stock/locations/", { params: { is_active: true, page_size: 100 } }),
    ]);
    rows.value = positionsResponse.data.positions || [];
    totals.value = positionsResponse.data.totals || {};
    locations.value = locationsResponse.data.results || locationsResponse.data;
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
@import "../styles/stock-document.css";

.stock-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.stock-kpi {
  display: flex; flex-direction: column; gap: 4px; padding: 16px 18px; text-align: left; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card);
  box-shadow: var(--shadow-sm); transition: border-color 120ms ease, background 120ms ease;
}
.stock-kpi:hover { border-color: var(--border-strong); }
.stock-kpi--on { border-color: var(--brand); background: var(--brand-subtle); }
.stock-kpi__label { color: var(--text-muted); font: var(--weight-bold) 11.5px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.stock-kpi__value { color: var(--text-strong); font-size: 24px; }
.stock-kpi small { color: var(--text-muted); font-size: 11.5px; }
.stock-kpi--warning .stock-kpi__value { color: var(--warning-text); }
.stock-kpi--danger .stock-kpi__value { color: var(--danger-text); }

.stock-pos__name { display: flex; flex-direction: column; gap: 2px; }
.stock-pos__name small { color: var(--text-muted); font-size: 11px; }
.stock-pos__num { font-variant-numeric: tabular-nums; }
.stock-pos__num--bad { color: var(--danger-text); font-weight: var(--weight-bold); }
.stock-pos__actions { display: flex; gap: 2px; }

.stock-pos__expansion { padding: 6px 12px 12px; }
.stock-pos__expansion h3 { margin: 0 0 8px; color: var(--text-strong); font-size: 13px; }
.stock-pos__expansion p { margin: 0; color: var(--text-muted); font-size: 12.5px; }
.stock-pos__expansion ul { margin: 0 0 8px; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 6px; }
.stock-pos__expansion li { display: flex; justify-content: space-between; gap: 12px; padding: 7px 10px; border-radius: var(--radius-md); background: var(--surface-ground); font-size: 12.5px; }
.stock-pos__expansion small { color: var(--text-muted); font-size: 11.5px; }

@media (max-width: 1080px) { .stock-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .stock-kpis { grid-template-columns: 1fr; } }
</style>
