<template>
  <div class="kds-root">
    <!-- ── Header ─────────────────────────────────────────────── -->
    <header class="kds-head">
      <!-- Select do quadro colado à esquerda -->
      <div class="kds-head__left">
        <div v-if="stations.length" class="kds-station-picker">
          <button type="button" class="kds-station-btn" @click="stationMenuOpen = !stationMenuOpen">
            <span class="kds-head__icon"><AppIcon name="soup" :size="16" /></span>
            <span class="kds-station-btn__name">{{ station ? station.name : "Selecionar quadro" }}</span>
            <AppIcon name="chevron-down" :size="13" />
          </button>
          <div v-if="stationMenuOpen" class="kds-station-menu">
            <button
              v-for="s in stations"
              :key="s.id"
              type="button"
              class="kds-station-opt"
              :class="{ 'kds-station-opt--active': station && station.id === s.id }"
              @click="selectStation(s)"
            >
              <span>{{ s.name }}</span>
              <small>{{ (s.columns || []).filter((c) => c.is_active).length }} colunas</small>
            </button>
          </div>
        </div>
        <span v-else class="kds-head__brand"><AppIcon name="soup" :size="16" /> KDS</span>
        <span class="kds-head__count">{{ boardItems.length }} {{ boardItems.length === 1 ? "item" : "itens" }}</span>
      </div>

      <div class="kds-head__actions">
        <!-- Filtro de datas -->
        <div class="kds-dr">
          <button
            v-for="opt in DATE_OPTIONS"
            :key="opt.key"
            type="button"
            class="kds-dr__btn"
            :class="{ 'kds-dr__btn--on': dateFilter === opt.key }"
            @click="setDateFilter(opt.key)"
          >
            {{ opt.label }}
          </button>
          <template v-if="dateFilter === 'custom'">
            <AppDateRange
              v-model="customPeriod"
              class="kds-dr__range"
              placeholder="Período personalizado"
            />
          </template>
        </div>

        <span class="kds-live"><span class="kds-live__dot" />Ao vivo</span>
        <button class="kds-refresh" type="button" :disabled="refreshing" @click="loadItems">
          <AppIcon name="refresh" :size="14" :class="{ 'kds-refresh__spin': refreshing }" />
          {{ updatedLabel }}
        </button>
      </div>
    </header>

    <div v-if="errorMsg" class="kds-error" role="alert" @click="errorMsg = ''">
      <AppIcon name="alert-circle" :size="15" /> {{ errorMsg }}
      <span class="kds-error__dismiss">✕</span>
    </div>

    <!-- ── Estados vazios ─────────────────────────────────────── -->
    <div v-if="!stations.length && !refreshing" class="kds-blank">
      <AppIcon name="layout-dashboard" :size="34" />
      <h2>Nenhum quadro de KDS</h2>
      <p>Crie um quadro e suas colunas para começar a operar a cozinha.</p>
      <button class="kds-blank__btn" type="button" @click="goToStations">Criar estação KDS</button>
    </div>

    <div v-else-if="station && !boardColumns.length" class="kds-blank">
      <AppIcon name="columns" :size="34" />
      <h2>Este quadro não tem colunas</h2>
      <p>Adicione colunas em "Estações KDS" — o quadro começa vazio de propósito.</p>
      <button class="kds-blank__btn" type="button" @click="goToStations">Criar colunas</button>
    </div>

    <div v-else-if="refreshing && !items.length" class="kds-board kds-board--loading" aria-label="Carregando pedidos da cozinha">
      <section v-for="column in Math.max(boardColumns.length, 3)" :key="column" class="kds-col kds-col--skeleton">
        <div class="app-skeleton kds-skeleton__title" />
        <div v-for="card in 3" :key="card" class="app-skeleton kds-skeleton__card" />
      </section>
    </div>

    <!-- ── Quadro (Kanban) ────────────────────────────────────── -->
    <div v-else class="kds-board">
      <section
        v-for="(column, ci) in boardColumns"
        :key="column.id"
        class="kds-col"
        :class="{ 'kds-col--dropping': dragOverColumnId === column.id }"
        :style="{ '--c': column.color }"
        @dragover.prevent="dragOverColumnId = column.id"
        @dragleave="onDragLeave(column.id)"
        @drop="onDrop(column)"
      >
        <header class="kds-col__head">
          <div class="kds-col__heading">
            <span class="kds-col__num">{{ ci + 1 }}</span>
            <span>{{ column.name }}</span>
            <span v-if="column.is_done" class="kds-col__flag">✓</span>
          </div>
          <strong>{{ columnItems(column).length }}</strong>
        </header>

        <div class="kds-col__body" @scroll="onColScroll($event, column)">
          <article
            v-for="item in columnCards(column)"
            :key="item.id"
            class="ticket"
            :class="{ 'ticket--urgent': isUrgent(item, column), 'ticket--dragging': dragItem && dragItem.id === item.id }"
            draggable="true"
            @dragstart="onDragStart(item)"
            @dragend="onDragEnd"
            @click="openModal(item)"
          >
            <div class="ticket__head">
              <span class="ticket__seq">#{{ item.order_sequence || shortId(item.order) }}</span>
              <span v-if="hasSla(column)" class="ticket__time" :class="{ 'ticket__time--urgent': isUrgent(item, column) }">
                <AppIcon name="clock" :size="11" />{{ elapsed(item.sent_to_kitchen_at || item.launched_at) }}
              </span>
            </div>

            <div class="ticket__context">
              <AppIcon :name="contextIcon(item)" :size="11" />{{ orderContextLabel(item) }}
              <span v-if="isAllRestaurants && item.restaurant_name" class="ticket__store">· {{ item.restaurant_name }}</span>
            </div>

            <div class="ticket__main">
              <span class="ticket__qty">{{ decimal(item.quantity) }}<small>x</small></span>
              <div class="ticket__title">
                <strong>{{ item.product_name }}</strong>
                <small v-if="item.variations && item.variations.length">
                  {{ item.variations.map((v) => v.name || v).join(", ") }}
                </small>
              </div>
            </div>

            <div v-if="item.customer_note" class="ticket__note">
              <AppIcon name="alert-circle" :size="11" /><span>{{ item.customer_note }}</span>
            </div>
          </article>

          <div v-if="hasMore(column)" class="kds-col__more">
            +{{ columnItems(column).length - visibleCount(column) }} — role para carregar
          </div>

          <div v-if="!columnItems(column).length" class="kds-col__empty">
            <span>{{ column.is_entry ? "Aguardando pedidos" : "Vazio" }}</span>
          </div>
        </div>
      </section>
    </div>

    <!-- ── Modal do card ──────────────────────────────────────── -->
    <div v-if="modalItem" class="kds-modal" @click.self="modalItem = null">
      <div class="kds-modal__box">
        <header class="kds-modal__head">
          <div>
            <h3>Pedido #{{ modalItem.order_sequence || shortId(modalItem.order) }}</h3>
            <span class="kds-modal__context">
              <AppIcon :name="contextIcon(modalItem)" :size="13" /> {{ orderContextLabel(modalItem) }}
              <template v-if="hasSla(modalColumn)">
                · <AppIcon name="clock" :size="12" /> {{ elapsed(modalItem.sent_to_kitchen_at || modalItem.launched_at) }}
              </template>
            </span>
          </div>
          <button class="kds-modal__close" type="button" @click="modalItem = null"><AppIcon name="x" :size="18" /></button>
        </header>

        <div class="kds-modal__col">
          Coluna atual: <strong>{{ modalColumnName }}</strong>
        </div>

        <div class="kds-modal__items">
          <div
            v-for="sib in orderItems(modalItem)"
            :key="sib.id"
            class="kds-modal__item"
            :class="{ 'kds-modal__item--focus': sib.id === modalItem.id }"
          >
            <span class="kds-modal__qty">{{ decimal(sib.quantity) }}x</span>
            <div class="kds-modal__item-main">
              <strong>{{ sib.product_name }}</strong>
              <small v-if="sib.variations && sib.variations.length">{{ sib.variations.map((v) => v.name || v).join(", ") }}</small>
              <small v-if="sib.addons && sib.addons.length" class="kds-modal__addons">
                + {{ sib.addons.map((a) => a.addon_name || a.name).filter(Boolean).join(", ") }}
              </small>
              <p v-if="sib.customer_note" class="kds-modal__note"><AppIcon name="alert-circle" :size="11" /> {{ sib.customer_note }}</p>
            </div>
            <span class="kds-modal__stat">{{ statusLabel(sib.status) }}</span>
          </div>
        </div>

        <footer class="kds-modal__foot">
          <button v-if="prevColumn" class="kds-modal__btn" type="button" :disabled="movingId === modalItem.id" @click="advanceModal(-1)">
            <AppIcon name="chevron-left" :size="15" /> Voltar
          </button>
          <button
            v-if="nextColumn"
            class="kds-modal__btn kds-modal__btn--primary"
            type="button"
            :disabled="movingId === modalItem.id"
            @click="advanceModal(1)"
          >
            Avançar para "{{ nextColumn.name }}" <AppIcon name="chevron-right" :size="15" />
          </button>
          <span v-else class="kds-modal__done"><AppIcon name="check-circle" :size="15" /> Última coluna</span>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import AppIcon from "../components/AppIcon.vue";
import AppDateRange from "../components/form/AppDateRange.vue";
import { api } from "../services/api";
import { useRealtimeResource } from "../composables/useRealtimeResource";
import { normalizeApiError } from "../utils/apiError";
import { currentMonthRange } from "../utils/dateRange";

const DEFAULT_SLA = 15;
const PAGE = 20; // cards renderizados por coluna antes de "carregar mais" no scroll
const router = useRouter();
useRealtimeResource("orders.orderitem", () => loadItems());

/* ── Filtro de datas (default: Hoje) ─────────────────────────── */
const DATE_OPTIONS = [
  { key: "today", label: "Hoje" },
  { key: "week", label: "Semana" },
  { key: "month", label: "Mês" },
  { key: "custom", label: "Personalizado" },
];
const dateFilter = ref("today");
const customPeriod = ref(currentMonthRange());

function ymdLocal(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const dateRange = computed(() => {
  const today = new Date();
  const end = ymdLocal(today);
  if (dateFilter.value === "week") {
    const s = new Date(today);
    s.setDate(today.getDate() - 6);
    return { after: ymdLocal(s), before: end };
  }
  if (dateFilter.value === "month") {
    return { after: ymdLocal(new Date(today.getFullYear(), today.getMonth(), 1)), before: end };
  }
  if (dateFilter.value === "custom") {
    const start = customPeriod.value?.[0];
    const finish = customPeriod.value?.[1] || start;
    return {
      after: start ? ymdLocal(start) : end,
      before: finish ? ymdLocal(finish) : end,
    };
  }
  return { after: end, before: end }; // hoje
});

function setDateFilter(key) {
  dateFilter.value = key;
}

const items = ref([]);
const stations = ref([]);
const slas = ref([]);
const station = ref(null);
const stationMenuOpen = ref(false);
const errorMsg = ref("");
const refreshing = ref(false);
const lastUpdated = ref(null);
const isAllRestaurants = !localStorage.getItem("starchef-restaurant-scope");

const dragItem = ref(null);
const dragOverColumnId = ref(null);
const movingId = ref("");
const modalItem = ref(null);

let refreshTimer = null;
let clockTimer = null;
const now = ref(Date.now());

/* ── Colunas do quadro selecionado ───────────────────────────── */
const boardColumns = computed(() =>
  [...((station.value && station.value.columns) || [])]
    .filter((c) => c.is_active)
    .sort((a, b) => a.position - b.position),
);
const columnIds = computed(() => new Set(boardColumns.value.map((c) => c.id)));
const entryColumn = computed(() => boardColumns.value.find((c) => c.is_entry) || boardColumns.value[0] || null);

/** Um item pertence a este quadro se casa com os setores da estação (ou todos). */
function belongsToBoard(item) {
  const sectors = station.value?.sectors || [];
  if (!sectors.length) return true;
  return sectors.includes(item.production_sector);
}
const boardItems = computed(() => items.value.filter(belongsToBoard));

/** Coluna efetiva de um item neste quadro (cai na entrada se ainda não posicionado). */
function effectiveColumnId(item) {
  if (item.kds_column && columnIds.value.has(item.kds_column)) return item.kds_column;
  return entryColumn.value ? entryColumn.value.id : null;
}
function columnItems(column) {
  return boardItems.value.filter((item) => effectiveColumnId(item) === column.id);
}

/* ── Paginação dinâmica por coluna: renderiza 20 e carrega +20 ao rolar ── */
const visible = reactive({});
function visibleCount(column) {
  return visible[column.id] ?? PAGE;
}
function columnCards(column) {
  return columnItems(column).slice(0, visibleCount(column));
}
function hasMore(column) {
  return columnItems(column).length > visibleCount(column);
}
function onColScroll(event, column) {
  const el = event.target;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 80 && hasMore(column)) {
    visible[column.id] = visibleCount(column) + PAGE;
  }
}
function resetVisible() {
  for (const key of Object.keys(visible)) delete visible[key];
}

/* ── SLA por coluna (reutilizável): coluna → estação ──────────────
   O tempo e a urgência do card SÓ existem quando há um SLA ativo vinculado
   àquela coluna (ou ao quadro). Sem SLA, o card não mostra tempo nem alerta. */
function slaFor(column) {
  const byColumn = slas.value.find((s) => s.is_active && (s.columns || []).includes(column.id));
  if (byColumn) return byColumn;
  return slas.value.find((s) => s.is_active && (s.stations || []).includes(station.value?.id)) || null;
}
function hasSla(column) {
  return Boolean(column && !column.is_done && slaFor(column));
}
function thresholdFor(column) {
  const sla = slaFor(column);
  if (!sla) return null;
  return sla.alert_minutes || sla.target_minutes || DEFAULT_SLA;
}
function isUrgent(item, column) {
  if (!hasSla(column)) return false;
  const ref = item.sent_to_kitchen_at || item.launched_at;
  if (!ref) return false;
  return Math.floor((now.value - new Date(ref).getTime()) / 60000) >= thresholdFor(column);
}

/* ── Modal ───────────────────────────────────────────────────── */
function orderItems(item) {
  return boardItems.value.filter((i) => i.order === item.order);
}
const modalColumn = computed(() => {
  if (!modalItem.value) return null;
  const id = effectiveColumnId(modalItem.value);
  return boardColumns.value.find((c) => c.id === id) || null;
});
const modalColumnName = computed(() => modalColumn.value?.name || "—");
const modalIndex = computed(() => (modalColumn.value ? boardColumns.value.findIndex((c) => c.id === modalColumn.value.id) : -1));
const nextColumn = computed(() => (modalIndex.value >= 0 ? boardColumns.value[modalIndex.value + 1] || null : null));
const prevColumn = computed(() => (modalIndex.value > 0 ? boardColumns.value[modalIndex.value - 1] || null : null));

function openModal(item) {
  if (dragItem.value) return; // não abre no fim de um arraste
  modalItem.value = item;
}
async function advanceModal(delta) {
  const target = delta > 0 ? nextColumn.value : prevColumn.value;
  if (!target || !modalItem.value) return;
  await moveItem(modalItem.value, target);
  // Mantém o modal aberto no mesmo item (agora na nova coluna).
  modalItem.value = items.value.find((i) => i.id === modalItem.value.id) || null;
}

/* ── Drag & drop ─────────────────────────────────────────────── */
function onDragStart(item) {
  dragItem.value = item;
}
function onDragEnd() {
  dragItem.value = null;
  dragOverColumnId.value = null;
}
function onDragLeave(columnId) {
  if (dragOverColumnId.value === columnId) dragOverColumnId.value = null;
}
async function onDrop(column) {
  dragOverColumnId.value = null;
  const item = dragItem.value;
  dragItem.value = null;
  if (!item || effectiveColumnId(item) === column.id) return;
  await moveItem(item, column);
}

async function moveItem(item, column) {
  movingId.value = item.id;
  errorMsg.value = "";
  const previous = item.kds_column;
  item.kds_column = column.id; // otimista
  try {
    await api.post(`/kitchen/items/${item.id}/move/`, { column: column.id });
    await loadItems(); // reflete efeitos de status (concluir/iniciar preparo)
  } catch (err) {
    item.kds_column = previous; // desfaz
    errorMsg.value = normalizeApiError(err).message;
  } finally {
    movingId.value = "";
  }
}

/* ── Carga de dados ──────────────────────────────────────────── */
async function loadItems() {
  refreshing.value = true;
  try {
    const response = await api.get("/kitchen/items/", {
      params: {
        ordering: "sent_to_kitchen_at",
        page_size: 100, // máx. do backend; o board mostra itens ativos (poucos por natureza)
        launched_after: dateRange.value.after,
        launched_before: dateRange.value.before,
      },
    });
    items.value = response.data.results || response.data || [];
    lastUpdated.value = Date.now();
  } catch (err) {
    errorMsg.value = normalizeApiError(err).message;
  } finally {
    refreshing.value = false;
  }
}
async function loadStations() {
  try {
    const res = await api.get("/kitchen/stations/", { params: { is_active: true, page_size: 200 } });
    stations.value = res.data.results || res.data || [];
    if (!station.value || !stations.value.some((s) => s.id === station.value.id)) {
      station.value = stations.value[0] || null;
    } else {
      station.value = stations.value.find((s) => s.id === station.value.id);
    }
  } catch {
    stations.value = [];
  }
}
async function loadSlas() {
  try {
    const res = await api.get("/sla/", { params: { is_active: true, page_size: 200 }, skipRestaurantScope: true });
    slas.value = res.data.results || res.data || [];
  } catch {
    slas.value = [];
  }
}

function selectStation(s) {
  station.value = s;
  stationMenuOpen.value = false;
  resetVisible();
}
function goToStations() {
  router.push({ name: "kds-estacoes" });
}

/* ── Rótulos / helpers ───────────────────────────────────────── */
function orderContextLabel(item) {
  if (item.order_table_number) return `Mesa ${item.order_table_number}`;
  if (item.order_command_code) return `Comanda ${item.order_command_code}`;
  const typeMap = { table: "Mesa", counter: "Balcão", delivery: "Delivery", takeaway: "Retirada", command: "Comanda" };
  return typeMap[item.order_type] || "Pedido";
}
function contextIcon(item) {
  if (item.order_table_number) return "armchair";
  if (item.order_command_code) return "ticket";
  return { table: "armchair", counter: "store", delivery: "truck", takeaway: "shopping-bag", command: "ticket" }[item.order_type] || "receipt-text";
}
function statusLabel(s) {
  return { pending: "Pendente", sent: "Novo", preparing: "Preparo", ready: "Pronto", delivered: "Entregue" }[s] || s;
}
function decimal(value) {
  return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}
function shortId(value) {
  return value ? String(value).slice(0, 6) : "-";
}
function elapsed(value) {
  if (!value) return "-";
  const minutes = Math.max(0, Math.floor((now.value - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
const updatedLabel = computed(() => {
  if (refreshing.value) return "Atualizando...";
  if (!lastUpdated.value) return "Atualizar";
  const secs = Math.floor((now.value - lastUpdated.value) / 1000);
  if (secs < 5) return "Agora";
  if (secs < 60) return `há ${secs}s`;
  return `há ${Math.floor(secs / 60)}min`;
});

// Ao trocar o intervalo de datas, zera a paginação das colunas e recarrega.
watch(dateRange, () => {
  resetVisible();
  loadItems();
});

onMounted(() => {
  loadStations();
  loadItems();
  loadSlas();
  // Polling remains only as a safety net when an intermediary blocks WebSocket.
  refreshTimer = window.setInterval(loadItems, 120000);
  clockTimer = window.setInterval(() => { now.value = Date.now(); }, 1000);
});
onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
  if (clockTimer) window.clearInterval(clockTimer);
});
</script>

<style scoped>
.kds-root { display: flex; flex-direction: column; gap: 16px; height: 100%; min-height: 0; }
.kds-root > * { animation: soft-pop var(--motion-base) var(--motion-spring) both; }

/* ── Header ──────────────────────────────────────────────────── */
.kds-head {
  display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 10px 14px; flex-shrink: 0;
  border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm);
}
.kds-head__left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.kds-head__icon { display: grid; place-items: center; width: 28px; height: 28px; border-radius: var(--radius-sm); background: var(--brand-subtle); color: var(--text-brand); flex-shrink: 0; }
.kds-head__brand { display: inline-flex; align-items: center; gap: 8px; color: var(--text-strong); font: var(--weight-extra) 16px/1 var(--font-sans); }
.kds-head__count { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); white-space: nowrap; }
.kds-head__actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.kds-station-picker { position: relative; }
.kds-station-btn {
  display: flex; align-items: center; gap: 9px; height: 40px; padding: 0 12px 0 6px; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body);
}
.kds-station-btn__name { font: var(--weight-bold) 14.5px/1 var(--font-sans); color: var(--text-strong); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 220px; }
.kds-station-btn:hover { background: var(--surface-hover); }

/* Filtro de datas */
.kds-dr { display: inline-flex; align-items: center; gap: 2px; padding: 3px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-sunken); }
.kds-dr__btn { height: 28px; padding: 0 11px; border: none; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; font: var(--weight-semibold) 12.5px/1 var(--font-sans); }
.kds-dr__btn:hover { color: var(--text-strong); }
.kds-dr__btn--on { background: var(--surface-card); color: var(--text-strong); box-shadow: var(--shadow-sm); }
.kds-dr__range { width: 230px; }
.kds-dr__range :deep(.p-inputtext) { height: 30px; padding-block: 0; font-size: 12px; }
.kds-dr__range :deep(.p-datepicker-trigger) { width: 30px; padding: 0; }
.kds-station-menu {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 25; min-width: 220px; padding: 6px;
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: var(--shadow-lg);
}
.kds-station-opt { display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 8px 10px; text-align: left; cursor: pointer; border: none; border-radius: var(--radius-sm); background: transparent; }
.kds-station-opt:hover, .kds-station-opt--active { background: var(--nav-item-hover); }
.kds-station-opt span { color: var(--text-strong); font: var(--weight-bold) 12.5px/1.2 var(--font-sans); }
.kds-station-opt small { color: var(--text-muted); font: var(--weight-medium) 11px/1 var(--font-sans); }

.kds-live { display: inline-flex; align-items: center; gap: 6px; color: var(--success-text); font: var(--weight-bold) 11.5px/1 var(--font-sans); }
.kds-live__dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); animation: kds-pulse 1.6s infinite; }
@keyframes kds-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.kds-refresh { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; cursor: pointer; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.kds-refresh:hover:not(:disabled) { background: var(--surface-hover); }
.kds-refresh__spin { animation: kds-spin 0.9s linear infinite; }
@keyframes kds-spin { to { transform: rotate(360deg); } }

.kds-error { display: flex; align-items: center; gap: 9px; padding: 11px 14px; cursor: pointer; color: var(--danger-text); background: var(--danger-subtle); border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent); border-radius: var(--radius-md); font: var(--weight-semibold) 13px/1.4 var(--font-sans); }
.kds-error__dismiss { margin-left: auto; opacity: 0.6; }

/* ── Estados vazios ──────────────────────────────────────────── */
.kds-blank { flex: 1; display: grid; place-items: center; align-content: center; gap: 10px; text-align: center; padding: 40px 20px; color: var(--text-muted); border: 1px dashed var(--border); border-radius: var(--radius-lg); }
.kds-blank i { color: var(--text-subtle); }
.kds-blank h2 { margin: 0; color: var(--text-strong); font: var(--weight-bold) 18px/1.2 var(--font-sans); }
.kds-blank p { margin: 0; max-width: 380px; font: var(--weight-medium) 13.5px/1.5 var(--font-sans); }
.kds-blank__btn { margin-top: 6px; height: 40px; padding: 0 18px; cursor: pointer; border: none; border-radius: var(--radius-md); background: var(--brand); color: var(--on-brand); font: var(--weight-bold) 13.5px/1 var(--font-sans); }
.kds-blank__btn:hover { background: var(--brand-hover); }

/* ── Board ───────────────────────────────────────────────────── */
.kds-board { flex: 1; min-height: 0; display: flex; gap: 14px; overflow-x: auto; padding-bottom: 4px; align-items: stretch; scrollbar-width: none; }
.kds-board::-webkit-scrollbar { width: 0; height: 0; display: none; }
.kds-board--loading { pointer-events: none; }
.kds-col--skeleton { min-height: 420px; padding: 16px; }
.kds-skeleton__title { width: 48%; height: 18px; margin-bottom: 18px; }
.kds-skeleton__card { height: 116px; margin-bottom: 12px; }
.kds-col {
  flex: 0 0 clamp(240px, 26vw, 300px); display: flex; flex-direction: column; min-height: 0;
  border: 1px solid var(--border); border-top: 3px solid var(--c, var(--border-strong)); border-radius: var(--radius-lg);
  background: var(--surface-sunken); transition: background var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.kds-col--dropping { background: color-mix(in srgb, var(--c) 12%, var(--surface-card)); box-shadow: 0 0 0 2px var(--c) inset; }
.kds-col__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 11px 13px; border-bottom: 1px solid var(--border-subtle); }
.kds-col__heading { display: flex; align-items: center; gap: 8px; color: var(--text-strong); font: var(--weight-bold) 13px/1 var(--font-sans); }
.kds-col__num {
  width: 22px; height: 22px; display: inline-grid; place-items: center;
  border-radius: 50%; background: color-mix(in srgb, var(--c) 16%, var(--surface-card));
  border: 1.5px solid var(--c); color: var(--c); font: var(--weight-extra) 11.5px/1 var(--font-mono);
}
.kds-col__dot { width: 10px; height: 10px; border-radius: 50%; background: var(--c); }
.kds-col__flag { color: var(--success); font-weight: 900; }
.kds-col__head strong { color: var(--text-muted); font: var(--weight-extra) 14px/1 var(--font-mono); }
.kds-col__body { flex: 1; min-height: 0; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 9px; scrollbar-width: none; }
.kds-col__body::-webkit-scrollbar { width: 0; height: 0; display: none; }
.kds-col__more { padding: 8px; text-align: center; color: var(--text-subtle); font: var(--weight-semibold) 11px/1.3 var(--font-sans); }
.kds-col__empty { margin: auto; padding: 20px; text-align: center; color: var(--text-subtle); font: var(--weight-medium) 12px/1.4 var(--font-sans); }

/* ── Ticket (card) ───────────────────────────────────────────── */
.ticket {
  display: flex; flex-direction: column; gap: 7px; padding: 11px 12px; cursor: grab; user-select: none;
  border: 1px solid var(--border); border-left: 3px solid var(--c, var(--border-strong)); border-radius: var(--radius-md);
  background: var(--surface-card); box-shadow: var(--shadow-sm); transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.ticket { animation: soft-pop var(--motion-slow) var(--motion-spring) both; transition: transform var(--motion-base) var(--motion-spring), box-shadow var(--motion-base) ease, border-color var(--motion-base) ease; }
.ticket:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.ticket--dragging { transform: rotate(1.5deg) scale(1.02); }
.ticket:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.ticket:active { cursor: grabbing; }
.ticket--dragging { opacity: 0.45; }
.ticket--urgent { border-color: color-mix(in srgb, var(--danger) 45%, transparent); border-left-color: var(--danger); background: var(--danger-subtle); }
.ticket__head { display: flex; align-items: center; justify-content: space-between; }
.ticket__seq { color: var(--text-strong); font: var(--weight-extra) 14px/1 var(--font-mono); }
.ticket__time { display: inline-flex; align-items: center; gap: 4px; color: var(--text-muted); font: var(--weight-bold) 11.5px/1 var(--font-mono); }
.ticket__time--urgent { color: var(--danger-text); }
.ticket__context { display: flex; align-items: center; gap: 5px; color: var(--text-muted); font: var(--weight-semibold) 11.5px/1.2 var(--font-sans); }
.ticket__store { color: var(--text-subtle); }
.ticket__main { display: flex; align-items: flex-start; gap: 9px; }
.ticket__qty { color: var(--text-strong); font: var(--weight-extra) 17px/1 var(--font-sans); }
.ticket__qty small { font-size: 11px; color: var(--text-muted); }
.ticket__title { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ticket__title strong { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.25 var(--font-sans); }
.ticket__title small { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.3 var(--font-sans); }
.ticket__note { display: flex; align-items: flex-start; gap: 5px; padding: 6px 8px; border-radius: var(--radius-sm); background: var(--warning-subtle); color: var(--warning-text); font: var(--weight-semibold) 11.5px/1.35 var(--font-sans); }

/* ── Modal ───────────────────────────────────────────────────── */
.kds-modal { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; padding: 16px; background: rgba(0, 0, 0, 0.55); }
.kds-modal__box { width: min(480px, 100%); max-height: 88vh; display: flex; flex-direction: column; background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); overflow: hidden; }
.kds-modal__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 18px; border-bottom: 1px solid var(--border-subtle); }
.kds-modal__head h3 { margin: 0; color: var(--text-strong); font: var(--weight-extra) 18px/1.2 var(--font-sans); }
.kds-modal__context { display: inline-flex; align-items: center; gap: 5px; margin-top: 4px; color: var(--text-muted); font: var(--weight-semibold) 12px/1.3 var(--font-sans); }
.kds-modal__close { width: 34px; height: 34px; display: grid; place-items: center; cursor: pointer; border: none; border-radius: var(--radius-md); background: transparent; color: var(--text-muted); }
.kds-modal__close:hover { background: var(--surface-hover); color: var(--text-strong); }
.kds-modal__col { padding: 10px 18px; color: var(--text-muted); font: var(--weight-semibold) 12.5px/1 var(--font-sans); background: var(--surface-sunken); border-bottom: 1px solid var(--border-subtle); }
.kds-modal__col strong { color: var(--text-strong); }
.kds-modal__items { flex: 1; overflow-y: auto; padding: 12px 18px; display: flex; flex-direction: column; gap: 8px; }
.kds-modal__item { display: flex; align-items: flex-start; gap: 10px; padding: 10px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--surface-card); }
.kds-modal__item--focus { border-color: color-mix(in srgb, var(--brand) 40%, transparent); background: var(--brand-subtle); }
.kds-modal__qty { color: var(--text-strong); font: var(--weight-extra) 15px/1.2 var(--font-mono); }
.kds-modal__item-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.kds-modal__item-main strong { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.25 var(--font-sans); }
.kds-modal__item-main small { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.3 var(--font-sans); }
.kds-modal__addons { color: var(--text-subtle); }
.kds-modal__note { display: flex; align-items: center; gap: 5px; margin-top: 3px; color: var(--warning-text); font: var(--weight-semibold) 11.5px/1.3 var(--font-sans); }
.kds-modal__stat { color: var(--text-muted); font: var(--weight-bold) 10.5px/1.4 var(--font-sans); text-transform: uppercase; letter-spacing: 0.03em; }
.kds-modal__foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 18px; border-top: 1px solid var(--border-subtle); }
.kds-modal__btn { display: inline-flex; align-items: center; gap: 6px; height: 42px; padding: 0 16px; cursor: pointer; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body); font: var(--weight-bold) 13.5px/1 var(--font-sans); }
.kds-modal__btn:hover:not(:disabled) { background: var(--surface-hover); }
.kds-modal__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.kds-modal__btn--primary { margin-left: auto; background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
.kds-modal__btn--primary:hover:not(:disabled) { background: var(--brand-hover); }
.kds-modal__done { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; color: var(--success-text); font: var(--weight-bold) 13px/1 var(--font-sans); }

@media (max-width: 760px) {
  .kds-col { flex-basis: 82vw; }
}
</style>
