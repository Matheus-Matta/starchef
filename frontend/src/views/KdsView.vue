<template>
  <div class="kds-root">
    <!-- ── Header bar ─────────────────────────────────────────── -->
    <header class="kds-head">
      <div class="kds-head__title">
        <span class="kds-head__icon"><AppIcon name="soup" :size="18" /></span>
        <div>
          <h1>{{ station ? station.name : "Cozinha" }}</h1>
          <p>{{ totalActive }} {{ totalActive === 1 ? "item em produção" : "itens em produção" }}</p>
        </div>
      </div>

      <div class="kds-head__meta">
        <div v-for="column in columns" :key="`stat-${column.key}`" class="kds-stat" :style="{ '--stat-tone': column.tone }">
          <strong>{{ column.items.length }}</strong>
          <span>{{ column.title }}</span>
        </div>
      </div>

      <div class="kds-head__actions">
        <!-- Station picker (shown only when stations exist) -->
        <div v-if="stations.length" class="kds-station-picker">
          <button type="button" class="kds-station-btn" @click="stationMenuOpen = !stationMenuOpen">
            <AppIcon name="layers" :size="13" />
            <span>{{ station ? station.name : "Sem estação" }}</span>
            <AppIcon name="chevron-down" :size="12" />
          </button>
          <div v-if="stationMenuOpen" class="kds-station-menu">
            <button
              type="button"
              class="kds-station-opt"
              :class="{ 'kds-station-opt--active': !station }"
              @click="selectStation(null)"
            >
              <span>Sem estação</span>
              <small>SLA padrão {{ DEFAULT_SLA }} min</small>
            </button>
            <button
              v-for="s in stations"
              :key="s.id"
              type="button"
              class="kds-station-opt"
              :class="{ 'kds-station-opt--active': station?.id === s.id }"
              @click="selectStation(s)"
            >
              <span>{{ s.name }}</span>
              <small>SLA {{ s.sla_minutes }} min</small>
            </button>
          </div>
        </div>

        <span class="kds-live"><span class="kds-live__dot" />Ao vivo</span>
        <button class="kds-refresh" type="button" :disabled="refreshing" @click="loadItems">
          <AppIcon name="refresh" :size="14" :class="{ 'kds-refresh__spin': refreshing }" />
          {{ updatedLabel }}
        </button>
      </div>
    </header>

    <div v-if="errorMsg" class="kds-error" role="alert" @click="errorMsg = ''">
      <AppIcon name="alert-circle" :size="15" />
      {{ errorMsg }}
      <span class="kds-error__dismiss">✕</span>
    </div>

    <!-- ── Board ──────────────────────────────────────────────── -->
    <div class="kds-grid">
      <section
        v-for="column in columns"
        :key="column.key"
        class="kds-column"
        :style="{ '--column-tone': column.tone, '--column-bg': column.bg }"
      >
        <header class="kds-column__header">
          <div class="kds-column__heading">
            <span class="kds-column__dot" />
            <div>
              <span>{{ column.title }}</span>
              <small>{{ column.subtitle }}</small>
            </div>
          </div>
          <strong>{{ column.items.length }}</strong>
        </header>

        <div class="kds-column__body">
          <article
            v-for="item in column.items"
            :key="item.id"
            class="ticket"
            :style="{ '--ticket-tone': column.tone, '--ticket-bg': column.bg }"
            :class="{ 'ticket--urgent': isUrgent(item) }"
          >
            <div class="ticket__accent" />

            <div class="ticket__head">
              <div class="ticket__order">
                <span class="ticket__seq">#{{ item.order_sequence || shortId(item.order) }}</span>
                <span class="ticket__context">
                  <AppIcon :name="contextIcon(item)" :size="11" />{{ orderContextLabel(item) }}
                </span>
              </div>
              <span class="ticket__time" :class="{ 'ticket__time--urgent': isUrgent(item) }">
                <AppIcon name="clock" :size="12" />{{ elapsed(item.sent_to_kitchen_at || item.launched_at) }}
              </span>
            </div>

            <div class="ticket__tags">
              <span v-if="item.batch_number" class="ticket__tag ticket__tag--batch">
                <AppIcon name="layers" :size="10" />Rodada {{ item.batch_number }}
              </span>
              <span v-if="isAllRestaurants && item.restaurant_name" class="ticket__tag ticket__tag--store">
                <AppIcon name="store" :size="10" />{{ item.restaurant_name }}
              </span>
              <span v-if="isUrgent(item)" class="ticket__tag ticket__tag--urgent">
                <AppIcon name="zap" :size="10" />Atrasado
              </span>
            </div>

            <div class="ticket__main">
              <span class="ticket__quantity">{{ decimal(item.quantity) }}<small>x</small></span>
              <div class="ticket__title">
                <strong>{{ item.product_name }}</strong>
                <small v-if="item.variations && item.variations.length">
                  {{ item.variations.map((v) => v.name || v).join(", ") }}
                </small>
              </div>
            </div>

            <div v-if="item.customer_note" class="ticket__note">
              <AppIcon name="alert-circle" :size="12" />
              <p>{{ item.customer_note }}</p>
            </div>

            <button
              class="ticket__action"
              type="button"
              :disabled="loadingAction === item.id"
              @click="advance(item, column.key)"
            >
              <AppIcon :name="actionIcon(column.key)" :size="15" /> {{ actionLabel(column.key) }}
            </button>
          </article>

          <div v-if="!column.items.length" class="kds-column__empty">
            <AppIcon name="check-circle" :size="22" />
            <span>Nada por aqui</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";

import AppIcon from "../components/AppIcon.vue";
import { api } from "../services/api";

const DEFAULT_SLA = 15;

const items = ref([]);
const stations = ref([]);
const station = ref(null);
const stationMenuOpen = ref(false);
const loadingAction = ref("");
const errorMsg = ref("");
const refreshing = ref(false);
const lastUpdated = ref(null);
const isAllRestaurants = !localStorage.getItem("starchef-restaurant-scope");
let refreshTimer = null;
let clockTimer = null;
const now = ref(Date.now());

const urgentMinutes = computed(() => station.value?.sla_minutes ?? DEFAULT_SLA);

const columns = computed(() => [
  {
    key: "sent",
    title: "Novos",
    subtitle: "Aguardando preparo",
    tone: "var(--order-new)",
    bg: "var(--order-new-bg)",
    items: items.value.filter((item) => item.status === "sent"),
  },
  {
    key: "preparing",
    title: "Em preparo",
    subtitle: "Na bancada",
    tone: "var(--order-prep)",
    bg: "var(--order-prep-bg)",
    items: items.value.filter((item) => item.status === "preparing"),
  },
  {
    key: "ready",
    title: "Prontos",
    subtitle: "Aguardando entrega",
    tone: "var(--order-ready)",
    bg: "var(--order-ready-bg)",
    items: items.value.filter((item) => item.status === "ready"),
  },
]);

const totalActive = computed(() => items.value.length);

const updatedLabel = computed(() => {
  if (refreshing.value) return "Atualizando...";
  if (!lastUpdated.value) return "Atualizar";
  const secs = Math.floor((now.value - lastUpdated.value) / 1000);
  if (secs < 5) return "Agora";
  if (secs < 60) return `há ${secs}s`;
  return `há ${Math.floor(secs / 60)}min`;
});

async function loadItems() {
  refreshing.value = true;
  try {
    const params = { ordering: "sent_to_kitchen_at" };
    const response = await api.get("/kitchen/items/", { params });
    items.value = response.data.results || response.data || [];
    lastUpdated.value = Date.now();
  } catch (err) {
    errorMsg.value = err?.response?.data?.detail || "Erro ao carregar itens da cozinha.";
  } finally {
    refreshing.value = false;
  }
}

async function loadStations() {
  try {
    const res = await api.get("/kitchen/stations/", { params: { is_active: true } });
    stations.value = res.data.results || res.data || [];
  } catch {
    stations.value = [];
  }
}

async function advance(item, columnKey) {
  loadingAction.value = item.id;
  errorMsg.value = "";
  try {
    await api.post(`/kitchen/items/${item.id}/status/`, { status: nextStatus(columnKey) });
    await loadItems();
  } catch (err) {
    const detail = err?.response?.data?.detail;
    errorMsg.value = Array.isArray(detail) ? detail.join(" ") : detail || err?.message || "Erro ao atualizar status.";
  } finally {
    loadingAction.value = "";
  }
}

function selectStation(s) {
  station.value = s;
  stationMenuOpen.value = false;
}

function nextStatus(key) {
  return { sent: "preparing", preparing: "ready", ready: "delivered" }[key];
}
function actionLabel(key) {
  return { sent: "Iniciar preparo", preparing: "Marcar pronto", ready: "Entregar" }[key];
}
function actionIcon(key) {
  return { sent: "play", preparing: "check", ready: "check-check" }[key];
}
function orderContextLabel(item) {
  if (item.order_table_number) return `Mesa ${item.order_table_number}`;
  if (item.order_command_code) return `Comanda ${item.order_command_code}`;
  const typeMap = { table: "Mesa", counter: "Balcao", delivery: "Delivery", takeaway: "Retirada", command: "Comanda" };
  return typeMap[item.order_type] || "Pedido";
}
function contextIcon(item) {
  if (item.order_table_number) return "armchair";
  if (item.order_command_code) return "ticket";
  return { table: "armchair", counter: "store", delivery: "truck", takeaway: "shopping-bag", command: "ticket" }[item.order_type] || "receipt-text";
}
function isUrgent(item) {
  const ref = item.sent_to_kitchen_at || item.launched_at;
  if (!ref) return false;
  return Math.floor((now.value - new Date(ref).getTime()) / 60000) >= urgentMinutes.value;
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

onMounted(() => {
  loadItems();
  loadStations();
  refreshTimer = window.setInterval(loadItems, 30000);
  clockTimer = window.setInterval(() => { now.value = Date.now(); }, 1000);
});

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
  if (clockTimer) window.clearInterval(clockTimer);
});
</script>

<style scoped>
.kds-root {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Header ──────────────────────────────────────────────────── */
.kds-head {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
}

.kds-head__title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-right: auto;
}

.kds-head__icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--brand-subtle);
  color: var(--text-brand);
}

.kds-head__title h1 {
  margin: 0;
  color: var(--text-strong);
  font: var(--weight-extra) 19px/1.1 var(--font-sans);
}

.kds-head__title p {
  margin: 2px 0 0;
  color: var(--text-muted);
  font: var(--weight-semibold) 12px/1 var(--font-sans);
}

.kds-head__meta {
  display: flex;
  gap: 8px;
}

.kds-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 58px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--stat-tone) 9%, var(--surface-card));
  border: 1px solid color-mix(in srgb, var(--stat-tone) 22%, transparent);
}

.kds-stat strong {
  color: var(--stat-tone);
  font: var(--weight-extra) 18px/1 var(--font-mono);
}

.kds-stat span {
  color: var(--text-muted);
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
}

.kds-head__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── Station picker ──────────────────────────────────────────── */
.kds-station-picker {
  position: relative;
}

.kds-station-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  color: var(--text-body);
  font: var(--weight-semibold) 12.5px/1 var(--font-sans);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.kds-station-btn:hover {
  border-color: var(--brand-border);
  color: var(--text-brand);
}

.kds-station-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  min-width: 200px;
  padding: 6px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}

.kds-station-opt {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.kds-station-opt:hover,
.kds-station-opt--active {
  background: var(--nav-item-hover);
}

.kds-station-opt span {
  color: var(--text-strong);
  font: var(--weight-bold) 13px/1.2 var(--font-sans);
}

.kds-station-opt small {
  color: var(--text-muted);
  font: var(--weight-medium) 11px/1 var(--font-sans);
}

/* ── Live / refresh ──────────────────────────────────────────── */
.kds-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--success-text);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
}

.kds-live__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--success) 60%, transparent);
  animation: kds-pulse 2s infinite;
}

@keyframes kds-pulse {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--success) 55%, transparent); }
  70% { box-shadow: 0 0 0 7px color-mix(in srgb, var(--success) 0%, transparent); }
  100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--success) 0%, transparent); }
}

.kds-refresh {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  color: var(--text-body);
  font: var(--weight-semibold) 12.5px/1 var(--font-sans);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out);
}

.kds-refresh:hover:not(:disabled) {
  border-color: var(--brand-border);
  background: var(--surface-hover);
}

.kds-refresh:disabled { cursor: wait; opacity: 0.75; }
.kds-refresh__spin { animation: kds-spin 0.8s linear infinite; }

@keyframes kds-spin {
  to { transform: rotate(360deg); }
}

/* ── Error ───────────────────────────────────────────────────── */
.kds-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--danger-subtle);
  border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent);
  color: var(--danger-text);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
  cursor: pointer;
}

.kds-error__dismiss {
  margin-left: auto;
  opacity: 0.6;
  font-size: 12px;
}

/* ── Board grid ──────────────────────────────────────────────── */
.kds-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  align-items: start;
}

.kds-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.kds-column__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--column-tone) 28%, transparent);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--column-bg), transparent 80%), var(--surface-card);
  box-shadow: var(--shadow-xs);
}

.kds-column__heading {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.kds-column__heading > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.kds-column__dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--column-tone);
  box-shadow: 0 0 0 4px var(--column-bg);
}

.kds-column__header span {
  color: var(--text-strong);
  font: var(--weight-extra) 14px/1 var(--font-sans);
}

.kds-column__header small {
  color: var(--text-muted);
  font: var(--weight-semibold) 11px/1 var(--font-sans);
}

.kds-column__header strong {
  min-width: 28px;
  height: 28px;
  padding: 0 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--column-tone);
  color: #fff;
  font: var(--weight-extra) 13px/1 var(--font-mono);
}

.kds-column__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kds-column__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 120px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  color: var(--text-subtle);
  background: var(--surface-card);
  font: var(--weight-semibold) 12.5px/1.4 var(--font-sans);
}

/* ── Ticket ──────────────────────────────────────────────────── */
.ticket {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 11px;
  padding: 13px 14px 13px 18px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out), border-color var(--dur-base) var(--ease-out);
}

.ticket:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--ticket-tone) 36%, var(--border));
  box-shadow: var(--shadow-md);
}

.ticket--urgent {
  border-color: color-mix(in srgb, var(--danger) 45%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--danger) 16%, transparent), var(--shadow-sm);
}

.ticket__accent {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: var(--ticket-tone);
}

.ticket--urgent .ticket__accent { background: var(--danger); }

.ticket__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.ticket__order {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ticket__seq {
  color: var(--text-strong);
  font: var(--weight-extra) 15px/1 var(--font-mono);
}

.ticket__context {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font: var(--weight-bold) 10.5px/1 var(--font-sans);
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
}

.ticket__time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  padding: 5px 9px;
  border-radius: var(--radius-pill);
  background: var(--ticket-bg);
  color: var(--ticket-tone);
  font: var(--weight-bold) 12px/1 var(--font-mono);
}

.ticket__time--urgent {
  background: var(--danger-subtle);
  color: var(--danger-text);
}

.ticket__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ticket__tags:empty { display: none; }

.ticket__tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
}

.ticket__tag--batch { background: var(--brand-subtle); color: var(--text-brand); }
.ticket__tag--store { background: var(--surface-active); color: var(--text-muted); }
.ticket__tag--urgent { background: var(--danger-subtle); color: var(--danger-text); }

.ticket__main {
  display: flex;
  align-items: flex-start;
  gap: 11px;
}

.ticket__quantity {
  min-width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  background: var(--ticket-bg);
  color: var(--ticket-tone);
  font: var(--weight-extra) 18px/1 var(--font-mono);
}

.ticket__quantity small { font-size: 11px; margin-left: 1px; opacity: 0.8; }

.ticket__title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 2px;
}

.ticket__title strong {
  color: var(--text-strong);
  font: var(--weight-extra) 16px/1.25 var(--font-sans);
}

.ticket__title small {
  color: var(--text-muted);
  font: var(--weight-semibold) 12px/1.3 var(--font-sans);
}

.ticket__note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 11px;
  border-radius: var(--radius-md);
  border: 1px dashed color-mix(in srgb, var(--warning) 50%, var(--border));
  background: var(--warning-subtle);
  color: var(--warning-text);
}

.ticket__note p {
  margin: 0;
  color: var(--text-body);
  font: var(--weight-semibold) 12.5px/1.35 var(--font-sans);
}

.ticket__action {
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 12px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--ticket-tone);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 6px 16px color-mix(in srgb, var(--ticket-tone) 26%, transparent);
  font: var(--weight-extra) 12.5px/1 var(--font-sans);
  transition: filter var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}

.ticket__action:hover:not(:disabled) { filter: brightness(1.06); }
.ticket__action:active:not(:disabled) { transform: scale(0.985); }
.ticket__action:disabled { cursor: wait; opacity: 0.7; }

/* ── Responsive ──────────────────────────────────────────────── */
@media (max-width: 1080px) {
  .kds-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .kds-head__meta { order: 3; width: 100%; }
}

@media (max-width: 720px) {
  .kds-grid { grid-template-columns: 1fr; }
  .kds-head__title { margin-right: 0; }
  .kds-head__actions { margin-left: auto; }
}
</style>
