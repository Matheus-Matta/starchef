<template>
  <aside class="sidebar" :class="{ 'sidebar--mobile-open': mobileOpen }" :style="{ width: collapsed ? 'var(--sidebar-w-mini)' : 'var(--sidebar-w)' }">
    <div class="sidebar__brand" :style="brandStyle">
      <img :src="logoUrl" width="34" height="34" alt="StarChef" />
      <span v-if="!collapsed" class="sidebar__brand-name">Star<span>Chef</span></span>
      <button class="sidebar__close" type="button" aria-label="Fechar menu" @click="$emit('close')">
        <AppIcon name="x" :size="20" />
      </button>
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
          <template v-for="item in group.items" :key="item.id">
            <button
              type="button"
              class="sidebar__item"
              :class="{ 'sidebar__item--active': isItemActive(item) }"
              :title="item.label"
              :style="itemStyle(item.id)"
              :aria-expanded="item.children ? reportsOpen : undefined"
              @click="navigateItem(item)"
            >
              <span v-if="isItemActive(item)" class="sidebar__active-bar" />
              <AppIcon :name="item.icon" :size="18" />
              <span v-if="!collapsed" class="sidebar__item-label">{{ item.label }}</span>
              <span v-if="!collapsed && item.badge" class="sidebar__badge" :style="badgeStyle(item)">
                {{ item.badge }}
              </span>
              <AppIcon v-if="!collapsed && item.children" :name="reportsOpen ? 'chevron-down' : 'chevron-right'" :size="14" />
            </button>
            <div v-if="!collapsed && item.children && reportsOpen" class="sidebar__submenu">
              <button
                v-for="child in item.children"
                :key="child.id"
                type="button"
                class="sidebar__subitem"
                :class="{ 'sidebar__subitem--active': active === child.id }"
                @click="$emit('navigate', child.id)"
              >
                {{ child.label }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </nav>

    <div v-if="!collapsed" class="sidebar__footer">
      <div class="sidebar__scope">
        <span>{{ accountName }}</span>
        <small>{{ accessLabel }}</small>
      </div>
      <div class="sidebar__mobile-profile">
        <div class="sidebar__mobile-user">
          <span class="sidebar__mobile-avatar">{{ userInitial }}</span>
          <span class="sidebar__mobile-user-copy">
            <strong>{{ displayName }}</strong>
            <small>{{ user?.email || user?.username }}</small>
          </span>
        </div>
        <div class="sidebar__mobile-profile-actions">
          <RouterLink :to="{ name: 'docs' }" @click="$emit('close')">
            <AppIcon name="book-open" :size="17" />
            Ajuda
          </RouterLink>
          <button type="button" @click="$emit('toggle-theme')">
            <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="17" />
            {{ theme === "dark" ? "Tema claro" : "Tema escuro" }}
          </button>
          <button class="sidebar__mobile-logout" type="button" @click="$emit('logout')">
            <AppIcon name="log-out" :size="17" />
            Sair
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import AppIcon from "../components/AppIcon.vue";

const logoUrl = "/logoicon.png";

const props = defineProps({
  active: { type: String, default: "painel" },
  collapsed: { type: Boolean, default: false },
  user: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  restaurants: { type: Array, default: () => [] },
  selectedRestaurantId: { type: String, default: "" },
  scope: { type: Object, default: null },
  mobileOpen: { type: Boolean, default: false },
  theme: { type: String, default: "light" },
});

const emit = defineEmits(["navigate", "scope-change", "close", "toggle-theme", "logout"]);
const scopeOpen = ref(false);
const reportsOpen = ref(String(props.active).startsWith("relatorio"));
watch(() => props.active, (value) => {
  if (String(value).startsWith("relatorio")) reportsOpen.value = true;
});

const canSeeAllRestaurants = computed(() => Boolean(props.user?.is_superuser || props.user?.profile_type === "admin" || props.user?.profile_type === "owner"));
const canManage = computed(() => ["admin", "owner", "manager"].includes(props.user?.profile_type) || props.user?.is_superuser);

// Licenciamento modular: itens de modulos desabilitados nao sao renderizados.
// Superadmin (dono da plataforma) sobrepoe o licenciamento e enxerga todos os modulos.
const enabledModules = computed(() => props.user?.enabled_modules || ["base"]);
function hasModule(moduleName) {
  if (!moduleName || moduleName === "base") return true;
  if (props.user?.is_superuser) return true;
  return enabledModules.value.includes(moduleName);
}
const canUseCash = computed(() => ["admin", "owner", "manager", "cashier"].includes(props.user?.profile_type) || props.user?.is_superuser);
const accountName = computed(() => props.user?.account_name || "StarChef");
const restaurantName = computed(() => props.scope?.restaurantName || props.user?.restaurant_name || props.user?.account_name || "Restaurante");
const branchName = computed(() => props.scope?.branchName || props.user?.branch_name || "Todos os restaurantes");
const accessLabel = computed(() => (canSeeAllRestaurants.value ? "Acesso administrativo" : "Escopo restrito"));
const displayName = computed(() => props.user?.name || props.user?.username || "Operador");
const userInitial = computed(() => displayName.value.trim().charAt(0).toUpperCase() || "U");

// Secoes da sidebar. As secoes marcadas com `module` pertencem a um Modulo
// opcional: quando a conta nao tem o modulo, a SECAO INTEIRA some (nao so os itens).
// As secoes base (sem `module`) contem apenas itens do Modulo Base.
const groups = computed(() =>
  [
    {
      label: "Principal",
      items: [
        { id: "painel", label: "Home", icon: "home" },
        { id: "pedidos", label: "Pedidos", icon: "receipt-text", badge: formatBadge(props.stats.ordersOpen) },
        { id: "kds", label: "KDS Cozinha", icon: "soup", badge: formatBadge(props.stats.kitchenOpen), badgeTone: "warning" },
      ],
    },
    {
      label: "Operacao",
      items: [
        { id: "kds-estacoes", label: "Estacoes KDS", icon: "soup" },
        { id: "sla", label: "SLAs", icon: "timer" },
        { id: "mesas", label: "Mesas", icon: "armchair" },
        { id: "comandas", label: "Comandas", icon: "receipt" },
        canUseCash.value ? { id: "caixa", label: "Caixa", icon: "wallet" } : null,
        canUseCash.value ? { id: "formas-pagamento", label: "Formas de pagamento", icon: "credit-card" } : null,
        { id: "clientes", label: "Clientes", icon: "users" },
      ].filter(Boolean),
    },
    {
      label: "Cardapio",
      items: [
        { id: "cardapio", label: "Produtos", icon: "book-open" },
        { id: "categorias", label: "Categorias", icon: "tag" },
        { id: "adicionais", label: "Adicionais", icon: "plus" },
        canManage.value ? { id: "ingredientes", label: "Insumos", icon: "flask" } : null,
        canManage.value ? { id: "receitas", label: "Receitas", icon: "salad" } : null,
      ].filter(Boolean),
    },
    // ── Secoes de Modulos opcionais (ocultam por completo se o modulo estiver off) ──
    {
      label: "E-commerce",
      module: "ecommerce",
      items: [canManage.value ? { id: "cardapios", label: "Cardapios digitais", icon: "book-marked" } : null].filter(Boolean),
    },
    {
      label: "Entrega",
      module: "entrega",
      items: [
        canManage.value ? { id: "zonas-entrega", label: "Zonas de entrega", icon: "map-pin" } : null,
        canManage.value ? { id: "entregadores", label: "Entregadores", icon: "truck" } : null,
      ].filter(Boolean),
    },
    {
      label: "Logistica",
      module: "logistica",
      items: [
        canManage.value ? { id: "fornecedores", label: "Fornecedores", icon: "store" } : null,
        canManage.value ? { id: "estoque-posicao", label: "Posição de estoque", icon: "layers" } : null,
        canManage.value ? { id: "estoque-entradas", label: "Entradas", icon: "package" } : null,
        canManage.value ? { id: "estoque-saidas", label: "Saidas", icon: "truck" } : null,
        canManage.value ? { id: "estoque-lotes", label: "Lotes e validades", icon: "clipboard-list" } : null,
        canManage.value ? { id: "estoque", label: "Movimentacoes", icon: "clipboard-list" } : null,
        canManage.value ? { id: "locais-estoque", label: "Locais de estoque", icon: "map-pin" } : null,
        canManage.value ? { id: "etiquetas-estoque", label: "Modelos de etiqueta", icon: "tag" } : null,
        canManage.value ? { id: "configuracao-estoque", label: "Configuração do estoque", icon: "settings" } : null,
      ].filter(Boolean),
    },
    {
      label: "Financeiro",
      module: "financeiro",
      items: [
        canManage.value ? { id: "pagamentos", label: "Hist. pagamentos", icon: "dollar-sign" } : null,
        canManage.value ? { id: "notas-fiscais", label: "Notas fiscais", icon: "shield-check" } : null,
        canManage.value ? { id: "perfis-fiscais", label: "Perfis fiscais", icon: "percentage" } : null,
        canSeeAllRestaurants.value ? { id: "configuracao-cosmos", label: "Configuração Cosmos", icon: "search" } : null,
        canSeeAllRestaurants.value ? { id: "configuracao-focus", label: "Configuração Focus", icon: "settings" } : null,
      ].filter(Boolean),
    },
    {
      label: "Gestao",
      items: [
        canManage.value ? {
          id: "relatorios",
          label: "Relatórios",
          icon: "bar-chart-3",
          children: [
            { id: "relatorio-geral", label: "Visão geral" },
            { id: "relatorio-vendas", label: "Vendas" },
            { id: "relatorio-pedidos", label: "Pedidos" },
            { id: "relatorio-produtos", label: "Produtos" },
            { id: "relatorio-pagamentos", label: "Pagamentos" },
            { id: "relatorio-garcons", label: "Garçons" },
            { id: "relatorio-restaurantes", label: "Restaurantes" },
          ],
        } : null,
        canSeeAllRestaurants.value ? { id: "restaurantes", label: "Restaurantes", icon: "store" } : null,
        canManage.value ? { id: "setores", label: "Setores", icon: "armchair" } : null,
        canManage.value ? { id: "usuarios", label: "Usuarios", icon: "user-cog" } : null,
        canManage.value ? { id: "perfis", label: "Perfis de acesso", icon: "shield-check" } : null,
        canSeeAllRestaurants.value ? { id: "terminais", label: "Terminais do PDV", icon: "monitor" } : null,
        canSeeAllRestaurants.value ? { id: "impressoras", label: "Impressoras", icon: "zap" } : null,
        canSeeAllRestaurants.value ? { id: "balancas", label: "Balancas", icon: "scale" } : null,
      ].filter(Boolean),
    },
  ]
    // 1. oculta a SECAO inteira dos modulos que a conta nao tem.
    .filter((group) => hasModule(group.module))
    // 2. defensivo: remove itens marcados com modulo desabilitado.
    .map((group) => ({ ...group, items: group.items.filter((item) => hasModule(item.module)) }))
    // 3. remove secoes que ficaram vazias (ex.: sem permissao de perfil).
    .filter((group) => group.items.length),
);

const brandStyle = computed(() => ({
  padding: props.collapsed ? "0" : "0 20px",
  justifyContent: props.collapsed ? "center" : "flex-start",
}));

function itemStyle(id) {
  const item = groups.value.flatMap((group) => group.items).find((candidate) => candidate.id === id);
  const on = isItemActive(item || { id });
  return {
    padding: props.collapsed ? "0" : "0 10px",
    justifyContent: props.collapsed ? "center" : "flex-start",
    background: on ? "var(--nav-item-active)" : "transparent",
    color: on ? "var(--text-brand)" : "var(--text-body)",
    font: `${on ? "var(--weight-bold)" : "var(--weight-medium)"} 13.5px/1 var(--font-sans)`,
  };
}

function isItemActive(item) {
  return props.active === item.id || Boolean(item.children?.some((child) => child.id === props.active));
}

function navigateItem(item) {
  if (item.children) {
    reportsOpen.value = !reportsOpen.value;
    return;
  }
  emit("navigate", item.id);
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
  padding: 7px 10px;
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
  padding: 6px 11px 10px;
}

.sidebar__group {
  margin-top: 14px;
}

.sidebar__group-label {
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--text-subtle);
  padding: 5px 9px 8px;
}

.sidebar__items {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: 9px;
  /* Acompanha a densidade do resto. Estava em 40 px fixos, então reduzir os
     controles não mudava nada na barra e a redução "não aparecia". */
  height: var(--control-h-lg);
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

.sidebar__submenu {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 2px 0 6px 28px;
  padding-left: 12px;
  border-left: 1px solid var(--border);
  animation: soft-pop var(--motion-base) var(--motion-spring) both;
}

.sidebar__subitem {
  min-height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  text-align: left;
  font: var(--weight-medium) 12.5px/1.2 var(--font-sans);
}

.sidebar__subitem:hover { background: var(--nav-item-hover); color: var(--text-body); }
.sidebar__subitem--active { background: var(--nav-item-active); color: var(--text-brand); font-weight: var(--weight-bold); }

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

.sidebar__mobile-profile {
  display: none;
}

/* Botão de fechar o drawer — só aparece no modo mobile (media query abaixo). */
.sidebar__close {
  display: none;
  margin-left: auto;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-muted);
  border-radius: var(--radius-md);
  cursor: pointer;
  flex-shrink: 0;
}

.sidebar__close:hover {
  background: var(--nav-item-hover);
  color: var(--text-strong);
}

/* ── Mobile / tablet-retrato: sidebar vira um drawer off-canvas ──────────────
   Fica fora do fluxo (position: fixed) e desliza da esquerda. O AppLayout
   controla a abertura (mobileOpen) e renderiza o backdrop. */
@media (max-width: 900px) {
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    height: 100dvh;
    width: min(86vw, 320px) !important;
    transform: translateX(-100%);
    transition: transform var(--dur-base) var(--ease-out);
    box-shadow: var(--shadow-lg);
    z-index: 60;
  }

  .sidebar--mobile-open {
    transform: translateX(0);
  }

  .sidebar__close {
    display: inline-flex;
  }

  .sidebar__footer { display: flex; flex-direction: column; gap: 10px; }
  .sidebar__mobile-profile { display: flex; flex-direction: column; gap: 10px; }
  .sidebar__mobile-user { display: flex; align-items: center; gap: 10px; padding: 4px 2px; min-width: 0; }
  .sidebar__mobile-avatar {
    width: 38px; height: 38px; flex-shrink: 0; display: grid; place-items: center;
    border-radius: 50%; background: var(--brand); color: #fff;
    font: var(--weight-extra) 14px/1 var(--font-sans);
  }
  .sidebar__mobile-user-copy { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .sidebar__mobile-user-copy strong { color: var(--text-strong); font-size: 13px; }
  .sidebar__mobile-user-copy small { overflow: hidden; color: var(--text-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
  .sidebar__mobile-profile-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .sidebar__mobile-profile-actions button,
  .sidebar__mobile-profile-actions a {
    height: 40px; display: inline-flex; align-items: center; justify-content: center; gap: 7px;
    border: 1px solid var(--border); border-radius: var(--radius-md);
    background: var(--surface-card); color: var(--text-body);
    font: var(--weight-bold) 12px/1 var(--font-sans); text-decoration: none;
  }
  .sidebar__mobile-profile-actions .sidebar__mobile-logout { color: var(--danger-text); background: var(--danger-subtle); }
}
</style>
