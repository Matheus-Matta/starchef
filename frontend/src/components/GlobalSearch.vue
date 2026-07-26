<template>
  <div ref="root" class="gsearch">
    <div class="gsearch__box" :class="{ 'gsearch__box--open': open }">
      <AppIcon name="search" :size="16" />
      <input
        ref="inputEl"
        v-model="query"
        class="gsearch__input"
        type="text"
        placeholder="Buscar pedidos, clientes, produtos…"
        aria-label="Busca global"
        @focus="open = true"
        @input="onInput"
        @keydown="onKeydown"
      />
      <button v-if="query" class="gsearch__clear" type="button" aria-label="Limpar" @click="clear">
        <AppIcon name="x" :size="14" />
      </button>
      <kbd v-else>Ctrl K</kbd>
    </div>

    <div v-if="open && query.trim().length >= 2" class="gsearch__panel">
      <div v-if="loading" class="gsearch__state"><i class="pi pi-spin pi-spinner" /> Buscando…</div>
      <template v-else-if="flat.length">
        <div v-for="group in groups" :key="group.key" class="gsearch__group">
          <span class="gsearch__group-label">{{ group.label }}</span>
          <button
            v-for="item in group.items"
            :key="item._key"
            class="gsearch__item"
            :class="{ 'gsearch__item--active': item._idx === activeIndex }"
            type="button"
            @mouseenter="activeIndex = item._idx"
            @click="go(item)"
          >
            <span class="gsearch__item-icon"><i :class="group.icon" /></span>
            <span class="gsearch__item-text">
              <strong>{{ item._title }}</strong>
              <small v-if="item._subtitle">{{ item._subtitle }}</small>
            </span>
            <AppIcon name="arrow-right" :size="13" class="gsearch__item-arrow" />
          </button>
        </div>
      </template>
      <div v-else class="gsearch__state">Nenhum resultado para “{{ query.trim() }}”.</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

import AppIcon from "./AppIcon.vue";
import { api } from "../services/api";

const router = useRouter();

/**
 * Recursos pesquisáveis pela busca global. Cada um consulta o próprio endpoint
 * (com `?search=`) e define como exibir/rotear o resultado. `route` é o nome da
 * rota de listagem; a navegação vai para `${route}--view` (página de detalhe).
 */
const SEARCHABLE = [
  {
    key: "pedidos", label: "Pedidos", route: "pedidos", endpoint: "/orders/", icon: "pi pi-receipt",
    title: (r) => `Pedido #${r.sequence ?? r.id}`,
    subtitle: (r) => r.customer_name || (r.table_number ? `Mesa ${r.table_number}` : ""),
  },
  {
    key: "clientes", label: "Clientes", route: "clientes", endpoint: "/customers/", icon: "pi pi-user",
    title: (r) => r.name || `#${r.id}`,
    subtitle: (r) => r.phone || r.email || "",
  },
  {
    key: "cardapio", label: "Produtos", route: "cardapio", endpoint: "/menu/products/", icon: "pi pi-box",
    title: (r) => r.name || `#${r.id}`,
    subtitle: (r) => r.category_name || r.internal_code || "",
  },
  {
    key: "mesas", label: "Mesas", route: "mesas", endpoint: "/tables/", icon: "pi pi-th-large",
    title: (r) => `Mesa ${r.number ?? r.id}`,
    subtitle: (r) => r.sector_name || "",
  },
  {
    key: "usuarios", label: "Usuários", route: "usuarios", endpoint: "/users/", icon: "pi pi-users", globalScope: true,
    title: (r) => r.full_name || `${r.first_name || ""} ${r.last_name || ""}`.trim() || r.username || `#${r.id}`,
    subtitle: (r) => r.email || r.username || "",
  },
];

const root = ref(null);
const inputEl = ref(null);
const query = ref("");
const open = ref(false);
const loading = ref(false);
const groups = ref([]);
const flat = ref([]);
const activeIndex = ref(-1);

let debounce = null;
let token = 0;

function onInput() {
  open.value = true;
  const q = query.value.trim();
  clearTimeout(debounce);
  if (q.length < 2) {
    token++; // invalida buscas em voo
    groups.value = [];
    flat.value = [];
    loading.value = false;
    return;
  }
  debounce = setTimeout(() => runSearch(q), 250);
}

async function runSearch(q) {
  const my = ++token;
  loading.value = true;
  try {
    const settled = await Promise.allSettled(
      SEARCHABLE.map((s) =>
        api
          .get(s.endpoint, { params: { search: q, page_size: 5 }, skipRestaurantScope: !!s.globalScope })
          .then((res) => res.data.results || res.data || []),
      ),
    );
    if (my !== token) return; // resposta obsoleta — uma busca mais nova começou
    let idx = 0;
    const nextFlat = [];
    const nextGroups = SEARCHABLE.map((s, i) => {
      const rows = settled[i].status === "fulfilled" ? settled[i].value : [];
      const items = rows.map((r) => {
        const item = {
          id: r.id,
          _route: s.route,
          _title: s.title(r),
          _subtitle: s.subtitle(r),
          _key: `${s.key}-${r.id}`,
          _idx: idx++,
        };
        nextFlat.push(item);
        return item;
      });
      return { key: s.key, label: s.label, icon: s.icon, items };
    }).filter((g) => g.items.length);
    groups.value = nextGroups;
    flat.value = nextFlat;
    activeIndex.value = nextFlat.length ? 0 : -1;
  } finally {
    if (my === token) loading.value = false;
  }
}

function go(item) {
  if (!item?.id) return;
  open.value = false;
  query.value = "";
  groups.value = [];
  flat.value = [];
  router.push({ name: `${item._route}--view`, params: { id: item.id } });
}

function clear() {
  query.value = "";
  groups.value = [];
  flat.value = [];
  token++;
  inputEl.value?.focus();
}

function onKeydown(event) {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (flat.value.length) activeIndex.value = (activeIndex.value + 1) % flat.value.length;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (flat.value.length) activeIndex.value = (activeIndex.value - 1 + flat.value.length) % flat.value.length;
  } else if (event.key === "Enter") {
    const item = flat.value[activeIndex.value];
    if (item) go(item);
  } else if (event.key === "Escape") {
    open.value = false;
    inputEl.value?.blur();
  }
}

/* Ctrl/Cmd+K foca a busca de qualquer lugar; clique fora fecha o painel. */
function onGlobalKey(event) {
  if ((event.ctrlKey || event.metaKey) && (event.key === "k" || event.key === "K")) {
    event.preventDefault();
    open.value = true;
    inputEl.value?.focus();
  }
}
function onDocClick(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false;
}
onMounted(() => {
  document.addEventListener("keydown", onGlobalKey);
  document.addEventListener("click", onDocClick);
});
onUnmounted(() => {
  document.removeEventListener("keydown", onGlobalKey);
  document.removeEventListener("click", onDocClick);
});
</script>

<style scoped>
.gsearch {
  position: relative;
  margin-left: auto;
  min-width: 0;
}

.gsearch__box {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 40px;
  width: clamp(200px, 32vw, 300px);
  padding: 0 12px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-subtle);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.gsearch__box--open {
  border-color: var(--ring);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 20%, transparent);
}
.gsearch__input {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  outline: none;
  color: var(--text-body);
  font: var(--weight-medium) 13.5px/1 var(--font-sans);
}
.gsearch__input::placeholder { color: var(--text-subtle); }
.gsearch__box kbd {
  flex-shrink: 0;
  font: var(--weight-semibold) 10px/1 var(--font-mono, monospace);
  color: var(--text-subtle);
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 5px;
}
.gsearch__clear {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.gsearch__clear:hover { background: var(--surface-hover); color: var(--text-strong); }

/* ── Painel de resultados ─────────────────────────────────────────── */
.gsearch__panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 40;
  width: min(420px, 92vw);
  max-height: min(60vh, 440px);
  overflow-y: auto;
  padding: 6px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.gsearch__state {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  padding: 22px;
  color: var(--text-muted);
  font: var(--weight-medium) 13px/1.4 var(--font-sans);
  text-align: center;
}

.gsearch__group { display: flex; flex-direction: column; }
.gsearch__group + .gsearch__group { margin-top: 2px; }
.gsearch__group-label {
  padding: 8px 10px 4px;
  color: var(--text-subtle);
  font: var(--weight-bold) 10.5px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.gsearch__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-body);
  cursor: pointer;
  text-align: left;
}
.gsearch__item--active { background: var(--surface-hover); }
.gsearch__item-icon {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: var(--surface-sunken);
  color: var(--text-muted);
}
.gsearch__item-icon .pi { font-size: 0.85rem; }
.gsearch__item-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.gsearch__item-text strong {
  color: var(--text-strong);
  font: var(--weight-semibold) 13px/1.3 var(--font-sans);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gsearch__item-text small {
  color: var(--text-muted);
  font: var(--weight-medium) 11.5px/1.3 var(--font-sans);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gsearch__item-arrow { flex-shrink: 0; color: var(--text-subtle); opacity: 0; }
.gsearch__item--active .gsearch__item-arrow { opacity: 1; }

@media (max-width: 620px) {
  .gsearch__box { width: clamp(140px, 42vw, 240px); }
  .gsearch__box kbd { display: none; }
  .gsearch__panel { width: min(340px, 92vw); }
}

/* Em phones o topo fica apertado (menu + título + ações), então a busca
   global some — as listas têm busca própria e o PDV é acessado pelo menu. */
@media (max-width: 560px) {
  .gsearch { display: none; }
}
</style>
