<template>
  <aside class="sidebar" :style="{ width: collapsed ? 'var(--sidebar-w-mini)' : 'var(--sidebar-w)' }">
    <div class="sidebar__brand" :style="brandStyle">
      <img :src="logoUrl" width="34" height="34" alt="StarChef" />
      <span v-if="!collapsed" class="sidebar__brand-name">Star<span>Chef</span></span>
    </div>

    <div v-if="!collapsed" class="sidebar__scope-picker">
      <button class="sidebar__branch" type="button" :aria-expanded="scopeOpen" @click="toggleScope">
        <span class="sidebar__branch-icon">
          <AppIcon name="store" :size="16" />
        </span>
        <span class="sidebar__branch-text">
          <span class="sidebar__branch-title">{{ restaurantName }}</span>
          <span class="sidebar__branch-subtitle">{{ branchName }}</span>
        </span>
        <AppIcon v-if="canSeeAllRestaurants" name="chevrons-up-down" :size="15" />
      </button>

      <div v-if="scopeOpen && canSeeAllRestaurants" class="sidebar__scope-menu">
        <button
          type="button"
          class="sidebar__scope-option"
          :class="{ 'sidebar__scope-option--active': !selectedRestaurantId }"
          @click="selectScope('')"
        >
          <span>Todos os restaurantes</span>
          <small>Dados consolidados da conta</small>
        </button>
        <button
          v-for="restaurant in restaurants"
          :key="restaurant.id"
          type="button"
          class="sidebar__scope-option"
          :class="{ 'sidebar__scope-option--active': selectedRestaurantId === restaurant.id }"
          @click="selectScope(restaurant.id)"
        >
          <span>{{ restaurant.trade_name }}</span>
          <small>{{ restaurant.city || restaurant.legal_name || "Todas as filiais" }}</small>
        </button>
      </div>
    </div>

    <nav class="sidebar__nav">
      <div v-for="group in groups" :key="group.label" class="sidebar__group">
        <div v-if="!collapsed" class="sidebar__group-label">{{ group.label }}</div>
        <div class="sidebar__items">
          <button
            v-for="item in group.items"
            :key="item.id"
            type="button"
            class="sidebar__item"
            :class="{ 'sidebar__item--active': active === item.id }"
            :title="item.label"
            :style="itemStyle(item.id)"
            @click="$emit('navigate', item.id)"
          >
            <span v-if="active === item.id" class="sidebar__active-bar" />
            <AppIcon :name="item.icon" :size="18" />
            <span v-if="!collapsed" class="sidebar__item-label">{{ item.label }}</span>
            <span v-if="!collapsed && item.badge" class="sidebar__badge" :style="badgeStyle(item)">
              {{ item.badge }}
            </span>
          </button>
        </div>
      </div>
    </nav>

    <div v-if="!collapsed" class="sidebar__footer">
      <div class="sidebar__scope">
        <span>{{ accountName }}</span>
        <small>{{ accessLabel }}</small>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";

import logoUrl from "../assets/logo-mark.svg";
import AppIcon from "../components/AppIcon.vue";

const props = defineProps({
  active: { type: String, default: "painel" },
  collapsed: { type: Boolean, default: false },
  user: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  restaurants: { type: Array, default: () => [] },
  selectedRestaurantId: { type: String, default: "" },
  scope: { type: Object, default: null },
});

const emit = defineEmits(["navigate", "scope-change"]);
const scopeOpen = ref(false);

const canSeeAllRestaurants = computed(() => Boolean(props.user?.is_superuser || props.user?.profile_type === "admin"));
const canManage = computed(() => ["admin", "owner", "manager"].includes(props.user?.profile_type) || props.user?.is_superuser);
const canUseCash = computed(() => ["admin", "owner", "manager", "cashier"].includes(props.user?.profile_type) || props.user?.is_superuser);
const accountName = computed(() => props.user?.account_name || "StarChef");
const restaurantName = computed(() => props.scope?.restaurantName || props.user?.restaurant_name || props.user?.account_name || "Restaurante");
const branchName = computed(() => props.scope?.branchName || props.user?.branch_name || "Todas as filiais");
const accessLabel = computed(() => (canSeeAllRestaurants.value ? "Acesso administrativo" : "Escopo restrito"));

const groups = computed(() =>
  [
    {
      label: "Principal",
      items: [
        { id: "painel", label: "Painel", icon: "layout-dashboard" },
        { id: "pedidos", label: "Pedidos", icon: "receipt-text", badge: formatBadge(props.stats.ordersOpen) },
        { id: "kds", label: "KDS Cozinha", icon: "soup", badge: formatBadge(props.stats.kitchenOpen), badgeTone: "warning" },
      ],
    },
    {
      label: "Operacao",
      items: [
        { id: "kds-estacoes", label: "Estacoes KDS", icon: "soup" },
        { id: "mesas", label: "Mesas & Comandas", icon: "armchair" },
        canUseCash.value ? { id: "caixa", label: "Caixa", icon: "wallet" } : null,
        { id: "clientes", label: "Clientes", icon: "users" },
      ].filter(Boolean),
    },
    {
      label: "Cardapio",
      items: [
        { id: "cardapio", label: "Produtos", icon: "book-open" },
        { id: "categorias", label: "Categorias", icon: "tag" },
        { id: "adicionais", label: "Adicionais", icon: "plus" },
        canManage.value ? { id: "ingredientes", label: "Ingredientes", icon: "flask" } : null,
        canManage.value ? { id: "receitas", label: "Receitas", icon: "salad" } : null,
        canManage.value ? { id: "cardapios", label: "Cardapios digitais", icon: "book-marked" } : null,
      ].filter(Boolean),
    },
    {
      label: "Delivery",
      items: [
        canManage.value ? { id: "zonas-entrega", label: "Zonas de entrega", icon: "map-pin" } : null,
        canManage.value ? { id: "entregadores", label: "Entregadores", icon: "truck" } : null,
      ].filter(Boolean),
    },
    {
      label: "Financeiro",
      items: [
        canManage.value ? { id: "estoque", label: "Estoque", icon: "package" } : null,
        canManage.value ? { id: "locais-estoque", label: "Locais de estoque", icon: "clipboard-list" } : null,
        canUseCash.value ? { id: "formas-pagamento", label: "Formas de pagamento", icon: "wallet" } : null,
        canManage.value ? { id: "pagamentos", label: "Hist. pagamentos", icon: "dollar-sign" } : null,
        canManage.value ? { id: "notas-fiscais", label: "Notas fiscais", icon: "shield-check" } : null,
      ].filter(Boolean),
    },
    {
      label: "Gestao",
      items: [
        canManage.value ? { id: "relatorios", label: "Relatorios", icon: "bar-chart-3" } : null,
        canSeeAllRestaurants.value ? { id: "restaurantes", label: "Restaurantes", icon: "store" } : null,
        canSeeAllRestaurants.value ? { id: "filiais", label: "Filiais", icon: "map-pin" } : null,
        canManage.value ? { id: "usuarios", label: "Usuarios", icon: "user-cog" } : null,
        canManage.value ? { id: "perfis", label: "Perfis de acesso", icon: "shield-check" } : null,
        canSeeAllRestaurants.value ? { id: "impressoras", label: "Impressoras", icon: "zap" } : null,
      ].filter(Boolean),
    },
  ].filter((group) => group.items.length),
);

const brandStyle = computed(() => ({
  padding: props.collapsed ? "0" : "0 20px",
  justifyContent: props.collapsed ? "center" : "flex-start",
}));

function itemStyle(id) {
  const on = props.active === id;
  return {
    padding: props.collapsed ? "0" : "0 10px",
    justifyContent: props.collapsed ? "center" : "flex-start",
    background: on ? "var(--nav-item-active)" : "transparent",
    color: on ? "var(--text-brand)" : "var(--text-body)",
    font: `${on ? "var(--weight-bold)" : "var(--weight-medium)"} 13.5px/1 var(--font-sans)`,
  };
}

function badgeStyle(item) {
  const on = props.active === item.id;
  return {
    background: item.badgeTone === "warning" ? "var(--warning-subtle)" : on ? "var(--brand)" : "var(--surface-active)",
    color: item.badgeTone === "warning" ? "var(--warning-text)" : on ? "#fff" : "var(--text-muted)",
  };
}

function formatBadge(value) {
  if (!Number(value)) return "";
  return Number(value) > 99 ? "99+" : String(value);
}

function toggleScope() {
  if (!canSeeAllRestaurants.value) return;
  scopeOpen.value = !scopeOpen.value;
}

function selectScope(restaurantId) {
  scopeOpen.value = false;
  emit("scope-change", restaurantId);
}
</script>

<style scoped>
.sidebar {
  flex-shrink: 0;
  background: var(--surface-nav);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  transition: width var(--dur-base) var(--ease-out);
  overflow: hidden;
  position: sticky;
  top: 0;
  z-index: 35;
}

.sidebar__brand {
  height: var(--topbar-h);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 11px;
  border-bottom: 1px solid var(--border-subtle);
}

.sidebar__brand-name {
  font: var(--weight-extra) 20px/1 var(--font-sans);
  letter-spacing: -0.02em;
  color: var(--text-strong);
}

.sidebar__brand-name span {
  color: var(--brand);
}

.sidebar__scope-picker {
  position: relative;
  margin: 14px 14px 6px;
}

.sidebar__branch {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  color: var(--text-body);
}

.sidebar__branch-icon {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: var(--brand-subtle);
  color: var(--brand);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sidebar__branch-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sidebar__branch-title {
  font: var(--weight-bold) 13px/1.2 var(--font-sans);
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar__branch-subtitle {
  font: var(--weight-medium) 11px/1 var(--font-sans);
  color: var(--text-muted);
}

.sidebar__scope-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 25;
  padding: 6px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}

.sidebar__scope-option {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-body);
  text-align: left;
  cursor: pointer;
}

.sidebar__scope-option:hover,
.sidebar__scope-option--active {
  background: var(--nav-item-hover);
}

.sidebar__scope-option span {
  font: var(--weight-bold) 12.5px/1.15 var(--font-sans);
  color: var(--text-strong);
}

.sidebar__scope-option small {
  font: var(--weight-medium) 11px/1.15 var(--font-sans);
  color: var(--text-muted);
}

.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  padding: 8px 14px 14px;
}

.sidebar__group {
  margin-top: 14px;
}

.sidebar__group-label {
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--text-subtle);
  padding: 6px 10px 10px;
}

.sidebar__items {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: 11px;
  height: 40px;
  width: 100%;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-md);
  position: relative;
}

.sidebar__item:not(.sidebar__item--active):hover {
  background: var(--nav-item-hover) !important;
}

.sidebar__active-bar {
  position: absolute;
  left: -14px;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--brand);
}

.sidebar__item-label {
  flex: 1;
  text-align: left;
}

.sidebar__badge {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  font: var(--weight-bold) 11px/1 var(--font-mono);
}

.sidebar__footer {
  padding: 14px;
  border-top: 1px solid var(--border-subtle);
}

.sidebar__scope {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 10px;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.sidebar__scope span {
  font: var(--weight-bold) 12.5px/1.15 var(--font-sans);
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar__scope small {
  font: var(--weight-medium) 11px/1 var(--font-sans);
  color: var(--text-muted);
}

@media (max-width: 760px) {
  .sidebar {
    display: none;
  }
}
</style>
