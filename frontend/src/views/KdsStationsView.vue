<template>
  <div class="kstations">
    <header class="kstations__head">
      <div>
        <h1>Estações KDS</h1>
        <p>Crie os quadros e defina as colunas que o KDS vai exibir.</p>
      </div>
      <button class="kbtn kbtn--primary" type="button" @click="openStationForm()">
        <i class="pi pi-plus" /> Nova estação
      </button>
    </header>

    <div v-if="error" class="kalert" @click="error = ''"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <div class="kstations__body">
      <!-- ── Lista de estações (quadros) ─────────────────────────── -->
      <aside class="kstations__list">
        <div v-if="loadingStations" class="kmuted">Carregando…</div>
        <button
          v-for="s in stations"
          :key="s.id"
          type="button"
          class="kstation"
          :class="{ 'kstation--active': selected && selected.id === s.id }"
          @click="select(s)"
        >
          <div class="kstation__main">
            <strong>{{ s.name }}</strong>
            <small>{{ s.restaurant_name || "—" }}</small>
          </div>
          <span class="kstation__count">{{ (s.columns || []).length }} col.</span>
        </button>
        <div v-if="!loadingStations && !stations.length" class="kempty">Nenhuma estação ainda. Crie a primeira.</div>
      </aside>

      <!-- ── Colunas da estação selecionada ──────────────────────── -->
      <section class="kcols">
        <div v-if="!selected" class="kempty kempty--big">
          <i class="pi pi-table" />
          <span>Selecione uma estação para gerenciar as colunas do quadro.</span>
        </div>

        <template v-else>
          <div class="kcols__head">
            <div class="kcols__title">
              <h2>{{ selected.name }}</h2>
              <small>{{ selected.restaurant_name }} · SLA padrão {{ selected.sla_minutes }} min · {{ sectorNames(selected.sectors) }}</small>
            </div>
            <div class="kcols__actions">
              <button class="kbtn" type="button" @click="openStationForm(selected)"><i class="pi pi-pencil" /> Editar</button>
              <button class="kbtn kbtn--danger" type="button" @click="removeStation(selected)"><i class="pi pi-trash" /></button>
              <button class="kbtn kbtn--primary" type="button" @click="openColumnForm()"><i class="pi pi-plus" /> Nova coluna</button>
            </div>
          </div>

          <div class="kcols__list">
            <div v-for="(col, idx) in columns" :key="col.id" class="kcol" :style="{ '--c': col.color }">
              <span class="kcol__num">{{ idx + 1 }}</span>
              <span class="kcol__dot" />
              <div class="kcol__main">
                <strong>{{ col.name }}</strong>
                <div class="kcol__badges">
                  <span v-if="col.is_entry" class="kbadge kbadge--entry">Entrada</span>
                  <span v-if="col.is_done" class="kbadge kbadge--done">Concluído</span>
                  <span v-if="!col.is_active" class="kbadge">Inativa</span>
                </div>
              </div>
              <div class="kcol__tools">
                <button class="kicon" type="button" title="Subir" :disabled="idx === 0" @click="reorder(idx, -1)"><i class="pi pi-arrow-up" /></button>
                <button class="kicon" type="button" title="Descer" :disabled="idx === columns.length - 1" @click="reorder(idx, 1)"><i class="pi pi-arrow-down" /></button>
                <button class="kicon" type="button" title="Editar" @click="openColumnForm(col)"><i class="pi pi-pencil" /></button>
                <button class="kicon kicon--danger" type="button" title="Excluir" @click="removeColumn(col)"><i class="pi pi-times" /></button>
              </div>
            </div>
            <div v-if="!columns.length" class="kempty">
              Sem colunas. Adicione a primeira e marque-a como <strong>Entrada</strong>.
            </div>
          </div>
        </template>
      </section>
    </div>

    <!-- ── Modal: estação ──────────────────────────────────────────── -->
    <div v-if="stationForm.open" class="kmodal" @click.self="stationForm.open = false">
      <div class="kmodal__box">
        <h3>{{ stationForm.id ? "Editar estação" : "Nova estação" }}</h3>

        <div v-if="!stationForm.id && templateOptions.length > 1" class="ktpl">
          <span class="kfield-label">Começar de um modelo</span>
          <div class="ktpl__grid">
            <button
              v-for="t in templateOptions"
              :key="t.key || 'blank'"
              type="button"
              class="ktpl__card"
              :class="{ 'ktpl__card--on': stationForm.template === t.key }"
              @click="pickTemplate(t)"
            >
              <strong>{{ t.name }}</strong>
              <small>{{ t.description }}</small>
              <div v-if="t.columns && t.columns.length" class="ktpl__cols">
                <span v-for="(c, i) in t.columns" :key="i" class="ktpl__chip" :style="{ '--c': c.color }">{{ c.name }}</span>
              </div>
            </button>
          </div>
        </div>

        <label class="kfield">Nome do quadro<input v-model="stationForm.name" type="text" placeholder="ex: Cozinha quente" /></label>
        <label class="kfield">Restaurante
          <select v-model="stationForm.restaurant">
            <option value="">Selecione…</option>
            <option v-for="r in restaurants" :key="r.id" :value="r.id">{{ r.trade_name }}</option>
          </select>
        </label>
        <label class="kfield">SLA padrão (min)<input v-model.number="stationForm.sla_minutes" type="number" min="1" /></label>
        <label class="kfield">Setor (opcional)
          <select v-model="stationForm.sector">
            <option value="">Todos os setores</option>
            <option v-for="s in SECTORS" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
          <small class="ksectors__hint">Todos = recebe itens de qualquer setor. Um setor = só os itens dele aparecem no quadro.</small>
        </label>
        <label class="kcheck"><input v-model="stationForm.is_active" type="checkbox" /> Ativa</label>
        <div class="kmodal__actions">
          <button class="kbtn" type="button" @click="stationForm.open = false">Cancelar</button>
          <button class="kbtn kbtn--primary" type="button" :disabled="saving || !stationForm.name || !stationForm.restaurant" @click="saveStation">Salvar</button>
        </div>
      </div>
    </div>

    <!-- ── Modal: coluna ───────────────────────────────────────────── -->
    <div v-if="columnForm.open" class="kmodal" @click.self="columnForm.open = false">
      <div class="kmodal__box">
        <h3>{{ columnForm.id ? "Editar coluna" : "Nova coluna" }}</h3>
        <label class="kfield">Nome<input v-model="columnForm.name" type="text" placeholder="ex: Em preparo" /></label>
        <div class="kfield">
          <span>Cor</span>
          <div class="kcolorrow">
            <button
              v-for="c in PALETTE"
              :key="c"
              type="button"
              class="kswatch"
              :class="{ 'kswatch--on': columnForm.color === c }"
              :style="{ background: c }"
              @click="columnForm.color = c"
            />
            <input v-model="columnForm.color" type="color" class="kswatch-input" />
          </div>
        </div>
        <label class="kcheck"><input v-model="columnForm.is_entry" type="checkbox" /> Coluna de entrada <small>(cards novos aparecem aqui)</small></label>
        <label class="kcheck"><input v-model="columnForm.is_done" type="checkbox" /> Coluna final <small>(conclui o item ao mover para cá)</small></label>
        <label class="kcheck"><input v-model="columnForm.is_active" type="checkbox" /> Ativa</label>
        <div class="kmodal__actions">
          <button class="kbtn" type="button" @click="columnForm.open = false">Cancelar</button>
          <button class="kbtn kbtn--primary" type="button" :disabled="saving || !columnForm.name" @click="saveColumn">Salvar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const PALETTE = ["#64748b", "#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6"];
// Setores de produção (enum do produto). Vazio = a estação recebe itens de todos.
const SECTORS = [
  { value: "kitchen", label: "Cozinha" },
  { value: "bar", label: "Bar" },
  { value: "dessert", label: "Sobremesas" },
];

const stations = ref([]);
const restaurants = ref([]);
const templates = ref([]);
const selected = ref(null);
const loadingStations = ref(false);
const saving = ref(false);
const error = ref("");

const BLANK_TEMPLATE = { key: "", name: "Em branco", description: "Crie as colunas manualmente.", columns: [] };
const templateOptions = computed(() => [BLANK_TEMPLATE, ...templates.value]);

const columns = computed(() =>
  [...((selected.value && selected.value.columns) || [])].sort((a, b) => a.position - b.position),
);

const stationForm = reactive({ open: false, id: null, name: "", restaurant: "", sla_minutes: 15, is_active: true, template: "", sector: "" });

function sectorNames(codes) {
  if (!codes || !codes.length) return "Todos os setores";
  return codes.map((c) => SECTORS.find((s) => s.value === c)?.label || c).join(", ");
}
const columnForm = reactive({ open: false, id: null, name: "", color: PALETTE[1], is_entry: false, is_done: false, is_active: true });

async function loadStations(keepSelectedId) {
  loadingStations.value = true;
  try {
    // Tela de gestão: lista as estações de TODOS os restaurantes da conta
    // (cada uma mostra o restaurante). Sem isto, criar uma estação para um
    // restaurante diferente do escopo do topo a "esconderia" da lista.
    const res = await api.get("/kitchen/stations/", { params: { page_size: 200 }, skipRestaurantScope: true });
    stations.value = res.data.results || res.data || [];
    // Re-seleciona a estação atual (para refletir colunas atualizadas).
    const id = keepSelectedId || selected.value?.id;
    selected.value = stations.value.find((s) => s.id === id) || stations.value[0] || null;
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loadingStations.value = false;
  }
}

async function loadRestaurants() {
  try {
    const res = await api.get("/restaurants/", { params: { page_size: 200 }, skipRestaurantScope: true });
    restaurants.value = res.data.results || res.data || [];
  } catch {
    restaurants.value = [];
  }
}

async function loadTemplates() {
  try {
    const res = await api.get("/kitchen/stations/templates/");
    templates.value = res.data || [];
  } catch {
    templates.value = [];
  }
}

function pickTemplate(t) {
  stationForm.template = t.key;
  // Sugere o nome do modelo se o usuário ainda não digitou nada.
  if (t.key && !stationForm.name.trim()) stationForm.name = t.name;
  // Sugere o setor do modelo (o usuário pode ajustar depois).
  stationForm.sector = t.key && Array.isArray(t.sectors) && t.sectors.length ? t.sectors[0] : "";
}

function select(s) {
  selected.value = s;
}

/* ── Estação ─────────────────────────────────────────────────────── */
function openStationForm(station) {
  error.value = "";
  Object.assign(stationForm, {
    open: true,
    id: station?.id || null,
    name: station?.name || "",
    restaurant: station?.restaurant || "",
    sla_minutes: station?.sla_minutes ?? 15,
    is_active: station ? station.is_active : true,
    template: "",
    sector: Array.isArray(station?.sectors) ? (station.sectors[0] || "") : "",
  });
}

async function saveStation() {
  saving.value = true;
  error.value = "";
  try {
    // Nova estação a partir de um modelo → cria quadro + colunas de uma vez.
    if (!stationForm.id && stationForm.template) {
      const res = await api.post("/kitchen/stations/from-template/", {
        template: stationForm.template,
        name: stationForm.name,
        restaurant: stationForm.restaurant,
        sla_minutes: stationForm.sla_minutes,
        sectors: stationForm.sector ? [stationForm.sector] : [],
      });
      stationForm.open = false;
      await loadStations(res.data.id);
      return;
    }
    const payload = {
      name: stationForm.name,
      restaurant: stationForm.restaurant,
      sla_minutes: stationForm.sla_minutes,
      is_active: stationForm.is_active,
      sectors: stationForm.sector ? [stationForm.sector] : [],
    };
    let savedId = stationForm.id;
    if (stationForm.id) await api.patch(`/kitchen/stations/${stationForm.id}/`, payload);
    else savedId = (await api.post("/kitchen/stations/", payload)).data.id;
    stationForm.open = false;
    await loadStations(savedId);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

async function removeStation(station) {
  if (!window.confirm(`Excluir a estação "${station.name}" e suas colunas?`)) return;
  error.value = "";
  try {
    await api.delete(`/kitchen/stations/${station.id}/`);
    selected.value = null;
    await loadStations();
  } catch (err) {
    error.value = normalizeApiError(err).message;
  }
}

/* ── Coluna ──────────────────────────────────────────────────────── */
function openColumnForm(col) {
  error.value = "";
  Object.assign(columnForm, {
    open: true,
    id: col?.id || null,
    name: col?.name || "",
    color: col?.color || PALETTE[1],
    is_entry: col ? col.is_entry : columns.value.length === 0, // 1ª coluna já sugere "entrada"
    is_done: col ? col.is_done : false,
    is_active: col ? col.is_active : true,
  });
}

async function saveColumn() {
  saving.value = true;
  error.value = "";
  try {
    const nextPos = columns.value.length ? Math.max(...columns.value.map((c) => c.position)) + 1 : 0;
    const payload = {
      station: selected.value.id,
      name: columnForm.name,
      color: columnForm.color,
      is_entry: columnForm.is_entry,
      is_done: columnForm.is_done,
      is_active: columnForm.is_active,
    };
    if (columnForm.id) await api.patch(`/kitchen/columns/${columnForm.id}/`, payload);
    else await api.post("/kitchen/columns/", { ...payload, position: nextPos });
    columnForm.open = false;
    await loadStations(selected.value.id);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

async function removeColumn(col) {
  if (!window.confirm(`Excluir a coluna "${col.name}"?`)) return;
  error.value = "";
  try {
    await api.delete(`/kitchen/columns/${col.id}/`);
    await loadStations(selected.value.id);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  }
}

async function reorder(idx, delta) {
  const a = columns.value[idx];
  const b = columns.value[idx + delta];
  if (!a || !b) return;
  error.value = "";
  try {
    // Troca as posições das duas colunas vizinhas.
    await Promise.all([
      api.patch(`/kitchen/columns/${a.id}/`, { position: b.position }),
      api.patch(`/kitchen/columns/${b.id}/`, { position: a.position }),
    ]);
    await loadStations(selected.value.id);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  }
}

onMounted(() => {
  loadStations();
  loadRestaurants();
  loadTemplates();
});
</script>

<style scoped>
.kstations { display: flex; flex-direction: column; gap: 16px; height: 100%; min-height: 0; }
.kstations__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.kstations__head h1 { margin: 0; color: var(--text-strong); font: var(--weight-extra) 24px/1.15 var(--font-sans); }
.kstations__head p { margin: 4px 0 0; color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); }

.kalert {
  display: flex; align-items: center; gap: 9px; padding: 11px 14px; cursor: pointer;
  color: var(--danger-text); background: var(--danger-subtle);
  border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent); border-radius: var(--radius-md);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

.kstations__body { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); gap: 16px; flex: 1; min-height: 0; }

/* Lista de estações */
.kstations__list {
  display: flex; flex-direction: column; gap: 6px; padding: 10px; overflow: auto;
  border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card);
}
.kstation {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 11px 12px; text-align: left; cursor: pointer;
  border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--text-body);
}
.kstation:hover { background: var(--surface-hover); }
.kstation--active { background: var(--brand-subtle); border-color: color-mix(in srgb, var(--brand) 30%, transparent); }
.kstation__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.kstation__main strong { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.2 var(--font-sans); }
.kstation__main small { color: var(--text-muted); font: var(--weight-medium) 11.5px/1 var(--font-sans); }
.kstation__count { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-mono); white-space: nowrap; }

/* Painel de colunas */
.kcols {
  display: flex; flex-direction: column; gap: 12px; padding: 16px; overflow: auto;
  border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card);
}
.kcols__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.kcols__title h2 { margin: 0; color: var(--text-strong); font: var(--weight-extra) 18px/1.2 var(--font-sans); }
.kcols__title small { color: var(--text-muted); font: var(--weight-medium) 12px/1 var(--font-sans); }
.kcols__actions { display: flex; gap: 8px; flex-wrap: wrap; }
.kcols__list { display: flex; flex-direction: column; gap: 8px; }

.kcol {
  display: flex; align-items: center; gap: 12px; padding: 11px 12px;
  border: 1px solid var(--border); border-left: 3px solid var(--c, var(--border-strong));
  border-radius: var(--radius-md); background: var(--surface-sunken);
}
.kcol__num {
  flex-shrink: 0; width: 24px; height: 24px; display: inline-grid; place-items: center;
  border-radius: 50%; background: color-mix(in srgb, var(--c) 16%, var(--surface-card));
  border: 1.5px solid var(--c); color: var(--c);
  font: var(--weight-extra) 12px/1 var(--font-mono);
}
.kcol__dot { width: 12px; height: 12px; border-radius: 50%; background: var(--c); flex-shrink: 0; }
.kcol__main { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.kcol__main strong { color: var(--text-strong); font: var(--weight-bold) 14px/1.2 var(--font-sans); }
.kcol__badges { display: flex; gap: 6px; }
.kbadge { padding: 2px 8px; border-radius: 99px; font: var(--weight-bold) 10.5px/1.4 var(--font-sans); background: var(--surface-active); color: var(--text-muted); }
.kbadge--entry { background: var(--info-subtle); color: var(--info-text); }
.kbadge--done { background: var(--success-subtle); color: var(--success-text); }
.kcol__tools { display: flex; gap: 4px; }

.kicon {
  width: 30px; height: 30px; display: inline-grid; place-items: center; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-card); color: var(--text-muted);
}
.kicon:hover:not(:disabled) { background: var(--surface-hover); color: var(--text-strong); }
.kicon:disabled { opacity: 0.4; cursor: not-allowed; }
.kicon--danger:hover:not(:disabled) { background: var(--danger-subtle); color: var(--danger-text); }

.kbtn {
  display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 13px; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 13px/1 var(--font-sans);
}
.kbtn:hover:not(:disabled) { background: var(--surface-hover); border-color: var(--border-strong); }
.kbtn:disabled { opacity: 0.5; cursor: not-allowed; }
.kbtn--primary { background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
.kbtn--primary:hover:not(:disabled) { background: var(--brand-hover); border-color: var(--brand-hover); }
.kbtn--danger { color: var(--danger-text); }
.kbtn--danger:hover:not(:disabled) { background: var(--danger-subtle); border-color: color-mix(in srgb, var(--danger) 30%, transparent); }

.kempty { padding: 18px; text-align: center; color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); }
.kempty--big { flex: 1; display: grid; place-items: center; align-content: center; gap: 10px; }
.kempty--big i { font-size: 30px; color: var(--text-subtle); }
.kmuted { color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); padding: 10px; }

/* Modais */
.kmodal { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; padding: 16px; background: rgba(0, 0, 0, 0.5); }
.kmodal__box {
  width: min(440px, 100%); display: flex; flex-direction: column; gap: 12px; padding: 20px;
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg);
}
.kmodal__box h3 { margin: 0 0 4px; color: var(--text-strong); font: var(--weight-extra) 17px/1.2 var(--font-sans); }
.kmodal__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }

.kfield { display: flex; flex-direction: column; gap: 5px; color: var(--text-strong); font: var(--weight-bold) 12.5px/1.2 var(--font-sans); }
.kfield input, .kfield select {
  height: 38px; padding: 0 11px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-ground); color: var(--text-strong); font: var(--weight-medium) 13px/1 var(--font-sans);
}
.kcheck { display: flex; align-items: center; gap: 8px; color: var(--text-body); font: var(--weight-semibold) 13px/1.3 var(--font-sans); cursor: pointer; }
.kcheck small { color: var(--text-muted); font-weight: var(--weight-medium); }

/* Seletor de modelos (templates) */
.ktpl { display: flex; flex-direction: column; gap: 7px; }
.kfield-label { color: var(--text-strong); font: var(--weight-bold) 12.5px/1.2 var(--font-sans); }
.ktpl__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.ktpl__card {
  display: flex; flex-direction: column; gap: 3px; padding: 10px; text-align: left; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-ground); color: var(--text-body);
}
.ktpl__card:hover { border-color: var(--border-strong); background: var(--surface-hover); }
.ktpl__card--on { border-color: var(--brand); background: var(--brand-subtle); box-shadow: 0 0 0 1px var(--brand) inset; }
.ktpl__card strong { color: var(--text-strong); font: var(--weight-bold) 13px/1.2 var(--font-sans); }
.ktpl__card small { color: var(--text-muted); font: var(--weight-medium) 11px/1.3 var(--font-sans); }
.ktpl__cols { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.ktpl__chip {
  padding: 2px 7px; border-radius: 99px; font: var(--weight-bold) 9.5px/1.5 var(--font-sans); color: #fff;
  background: var(--c); border: 1px solid color-mix(in srgb, var(--c) 60%, #000 0%);
}

.ksectors__hint { color: var(--text-muted); font: var(--weight-medium) 11px/1.4 var(--font-sans); }

.kcolorrow { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kswatch { width: 26px; height: 26px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; }
.kswatch--on { border-color: var(--text-strong); box-shadow: 0 0 0 2px var(--surface-card) inset; }
.kswatch-input { width: 40px; height: 30px; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-sm); background: none; cursor: pointer; }

@media (max-width: 760px) {
  .kstations__body { grid-template-columns: 1fr; }
}
</style>
