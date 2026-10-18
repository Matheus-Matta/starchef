<template>
  <Card title="Mapa de calor" :subtitle="subtitle">
    <template #actions>
      <div class="sales-heatmap__toggles">
        <div class="sales-heatmap__segment" role="group" aria-label="Origem">
          <button v-for="opt in origins" :key="opt.id" type="button" :class="{ 'is-active': origin === opt.id }" @click="origin = opt.id">{{ opt.label }}</button>
        </div>
        <div class="sales-heatmap__segment" role="group" aria-label="Medida">
          <button v-for="opt in measures" :key="opt.id" type="button" :class="{ 'is-active': measure === opt.id }" @click="measure = opt.id">{{ opt.label }}</button>
        </div>
      </div>
    </template>

    <p v-if="!rows.length" class="sales-heatmap__empty">Sem movimento no período.</p>
    <div v-else class="sales-heatmap__scroll">
      <div class="sales-heatmap__grid">
        <div />
        <div v-for="hour in 24" :key="`h${hour}`" class="sales-heatmap__hour">{{ hourLabel(hour - 1) }}</div>
        <template v-for="row in rows" :key="row.key">
          <div class="sales-heatmap__label">
            <strong>{{ row.label }}</strong>
            <small>{{ shortDate(row.key) }}</small>
          </div>
          <div
            v-for="cell in row.cells"
            :key="cell.hour"
            class="sales-heatmap__cell"
            :data-level="level(cell)"
            :title="tooltip(row, cell)"
          />
        </template>
      </div>
    </div>

    <div class="sales-heatmap__legend" aria-hidden="true">
      <span>Menos</span>
      <i v-for="n in 5" :key="n" class="sales-heatmap__cell" :data-level="n - 1" />
      <span>Mais</span>
    </div>
  </Card>
</template>

<script setup>
import { computed, ref } from "vue";

import Card from "../display/Card.vue";

const props = defineProps({
  // `heatmap` do /reports/sales/: a semana atual, domingo a sábado × 24 horas.
  heatmap: { type: Object, default: () => ({}) },
});

const origins = [
  { id: "all", label: "Tudo" },
  { id: "command", label: "Comanda" },
  { id: "counter", label: "Balcão" },
];
const measures = [
  { id: "items", label: "Itens" },
  { id: "total", label: "Valor" },
];
const origin = ref("all");
const measure = ref("items");

const rows = computed(() => props.heatmap?.rows || []);
// A semana é sempre a atual, qualquer que seja o período do relatório.
const subtitle = computed(() => {
  const { start, end } = props.heatmap || {};
  const semana = start && end ? `Semana atual · ${shortDate(start)} a ${shortDate(end)}` : "Semana atual";
  return `${semana} · itens pela hora em que entraram (comanda na anotação, balcão no lançamento)`;
});

function value(cell) {
  const pick = (kind) => Number(cell[`${kind}_${measure.value}`] || 0);
  if (origin.value === "all") return pick("command") + pick("counter");
  return pick(origin.value);
}

const maxValue = computed(() =>
  rows.value.reduce((max, row) => row.cells.reduce((m, cell) => Math.max(m, value(cell)), max), 0),
);

// Quatro tons acima do vazio, relativos ao pico do período: o que importa é
// onde o movimento se concentra, não o número absoluto.
function level(cell) {
  const v = value(cell);
  if (!v || !maxValue.value) return 0;
  return Math.max(1, Math.ceil((v / maxValue.value) * 4));
}

const money = (v) => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const items = (n) => `${n} ${Number(n) === 1 ? "item" : "itens"}`;
const hourLabel = (h) => `${String(h).padStart(2, "0")}:00`;

function shortDate(iso) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function tooltip(row, cell) {
  const day = `${row.label}, ${shortDate(row.key)}`;
  return [
    `${day} · ${hourLabel(cell.hour)}–${String(cell.hour).padStart(2, "0")}:59`,
    `Comanda: ${items(cell.command_items)} (${money(cell.command_total)})`,
    `Balcão: ${items(cell.counter_items)} (${money(cell.counter_total)})`,
  ].join("\n");
}
</script>

<style scoped>
.sales-heatmap__toggles { display: flex; flex-wrap: wrap; gap: 8px; }
.sales-heatmap__segment {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}
.sales-heatmap__segment button {
  padding: 5px 10px;
  border: 0;
  border-radius: calc(var(--radius-md) - 2px);
  background: transparent;
  color: var(--text-muted);
  font: var(--weight-medium) 12px/1.2 var(--font-sans);
  cursor: pointer;
}
.sales-heatmap__segment button.is-active { background: var(--surface-raised); color: var(--text-body); }
.sales-heatmap__scroll { overflow-x: auto; }
.sales-heatmap__grid {
  display: grid;
  grid-template-columns: 96px repeat(24, minmax(22px, 1fr));
  gap: 4px;
  min-width: 720px;
}
.sales-heatmap__label { display: flex; flex-direction: column; justify-content: center; text-align: right; padding-right: 8px; }
.sales-heatmap__label strong { color: var(--text-body); font: var(--weight-bold) 12px/1.2 var(--font-sans); }
.sales-heatmap__label small { color: var(--text-muted); font-size: 11px; }
.sales-heatmap__cell {
  display: block;
  aspect-ratio: 1;
  border-radius: 4px;
  border: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
}
.sales-heatmap__cell[data-level="1"] { background: color-mix(in srgb, var(--brand) 25%, transparent); border-color: transparent; }
.sales-heatmap__cell[data-level="2"] { background: color-mix(in srgb, var(--brand) 50%, transparent); border-color: transparent; }
.sales-heatmap__cell[data-level="3"] { background: color-mix(in srgb, var(--brand) 75%, transparent); border-color: transparent; }
.sales-heatmap__cell[data-level="4"] { background: var(--brand); border-color: transparent; }
.sales-heatmap__hour { color: var(--text-muted); font: var(--weight-medium) 10px/1 var(--font-sans); text-align: center; white-space: nowrap; }
.sales-heatmap__legend { display: flex; align-items: center; justify-content: flex-end; gap: 4px; margin-top: 12px; color: var(--text-muted); font-size: 11px; }
.sales-heatmap__legend .sales-heatmap__cell { width: 14px; }
.sales-heatmap__empty { color: var(--text-muted); }
</style>
