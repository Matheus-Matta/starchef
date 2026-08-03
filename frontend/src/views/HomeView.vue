<template>
  <div class="mobile-home">
    <section class="mobile-home__welcome">
      <div>
        <span>{{ greeting }}</span>
        <h1>{{ displayName }}</h1>
        <p>{{ restaurantName }}</p>
      </div>
    </section>

    <section class="mobile-home__highlights">
      <button v-for="item in highlights" :key="item.route" type="button" @click="go(item.route)">
        <span class="mobile-home__shortcut-icon" :data-tone="item.tone"><AppIcon :name="item.icon" :size="20" /></span>
        <strong>{{ item.label }}</strong>
        <small>{{ item.caption }}</small>
      </button>
    </section>

    <section v-for="group in visibleGroups" :key="group.label" class="mobile-home__group">
      <div class="mobile-home__group-head">
        <h2>{{ group.label }}</h2>
        <span>{{ group.items.length }} atalhos</span>
      </div>
      <div class="mobile-home__links">
        <button v-for="item in group.items" :key="item.route" type="button" @click="go(item.route)">
          <span><AppIcon :name="item.icon" :size="18" /></span>
          <strong>{{ item.label }}</strong>
          <AppIcon name="chevron-right" :size="15" />
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

import AppIcon from "../components/AppIcon.vue";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const canManage = computed(() => auth.user?.is_superuser || ["admin", "owner", "manager"].includes(auth.user?.profile_type));
const canUseCash = computed(() => auth.user?.is_superuser || ["admin", "owner", "manager", "cashier"].includes(auth.user?.profile_type));
const canSeeAll = computed(() => auth.user?.is_superuser || auth.user?.profile_type === "admin");
const enabledModules = computed(() => auth.user?.enabled_modules || ["base"]);
const hasModule = (name) => !name || name === "base" || auth.user?.is_superuser || enabledModules.value.includes(name);
const displayName = computed(() => auth.user?.name || auth.user?.username || "Operador");
const restaurantName = computed(() => auth.user?.restaurant_name || auth.user?.account_name || "StarChef");
const greeting = computed(() => new Date().getHours() < 12 ? "Bom dia" : new Date().getHours() < 18 ? "Boa tarde" : "Boa noite");

const highlights = computed(() => [
  { route: "pdv", label: "Novo pedido", caption: "Abrir o ponto de venda", icon: "plus", tone: "brand" },
  { route: "pedidos", label: "Pedidos", caption: "Acompanhar atendimento", icon: "receipt-text", tone: "warning" },
  { route: "kds", label: "Cozinha", caption: "Ver produção agora", icon: "soup", tone: "success" },
  { route: "relatorio-geral", label: "Relatório geral", caption: "Indicadores e vendas", icon: "bar-chart-3", tone: "info" },
]);

const groups = computed(() => [
  { label: "Operação", items: [
    { route: "mesas", label: "Mesas", icon: "armchair" },
    { route: "comandas", label: "Comandas", icon: "ticket" },
    canUseCash.value && { route: "caixa", label: "Caixa", icon: "wallet" },
    canUseCash.value && { route: "formas-pagamento", label: "Formas de pagamento", icon: "credit-card" },
    { route: "clientes", label: "Clientes", icon: "users" },
    { route: "kds-estacoes", label: "Estações KDS", icon: "soup" },
  ].filter(Boolean) },
  { label: "Cardápio", items: [
    { route: "cardapio", label: "Produtos", icon: "book-open" },
    { route: "categorias", label: "Categorias", icon: "tag" },
    { route: "adicionais", label: "Adicionais", icon: "plus" },
    canManage.value && { route: "ingredientes", label: "Ingredientes", icon: "flask" },
    canManage.value && { route: "receitas", label: "Receitas", icon: "salad" },
  ].filter(Boolean) },
  { label: "Gestão", items: [
    canManage.value && { route: "relatorios", label: "Relatórios avançados", icon: "bar-chart-3" },
    canManage.value && hasModule("logistica") && { route: "estoque", label: "Estoque", icon: "package" },
    canManage.value && hasModule("financeiro") && { route: "pagamentos", label: "Pagamentos", icon: "dollar-sign" },
    canSeeAll.value && { route: "restaurantes", label: "Restaurantes", icon: "store" },
    canManage.value && { route: "usuarios", label: "Usuários", icon: "user-cog" },
    canSeeAll.value && { route: "impressoras", label: "Impressoras", icon: "zap" },
    canSeeAll.value && { route: "balancas", label: "Balanças", icon: "scale" },
  ].filter(Boolean) },
]);
const visibleGroups = computed(() => groups.value.filter((group) => group.items.length));

function go(name) { router.push({ name }); }
</script>

<style scoped>
.mobile-home { display: flex; flex-direction: column; gap: 22px; padding-bottom: 14px; }
.mobile-home__welcome { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 6px 2px; }
.mobile-home__welcome span { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.mobile-home__welcome h1 { margin: 5px 0 3px; color: var(--text-strong); font: var(--weight-extra) 25px/1 var(--font-sans); }
.mobile-home__welcome p { margin: 0; color: var(--text-muted); font-size: 12px; }
.mobile-home__highlights { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.mobile-home__highlights > button { min-height: 132px; padding: 15px; display: flex; flex-direction: column; align-items: flex-start; gap: 7px; text-align: left; border: 1px solid var(--border); border-radius: 18px; background: var(--surface-card); box-shadow: var(--shadow-sm); cursor: pointer; animation: soft-pop var(--motion-slow) var(--motion-spring) both; }
.mobile-home__highlights > button:nth-child(2) { animation-delay: 45ms; }
.mobile-home__highlights > button:nth-child(3) { animation-delay: 90ms; }
.mobile-home__highlights > button:nth-child(4) { animation-delay: 135ms; }
.mobile-home__highlights > button:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--brand) 30%, var(--border)); box-shadow: var(--shadow-md); }
.mobile-home__highlights > button:hover .mobile-home__shortcut-icon { transform: rotate(-3deg) scale(1.08); }
.mobile-home__shortcut-icon { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; color: var(--brand); background: var(--brand-subtle); transition: transform var(--motion-base) var(--motion-spring); }
.mobile-home__shortcut-icon[data-tone="warning"] { color: var(--warning-text); background: var(--warning-subtle); }
.mobile-home__shortcut-icon[data-tone="success"] { color: var(--success-text); background: var(--success-subtle); }
.mobile-home__shortcut-icon[data-tone="info"] { color: var(--info-text); background: var(--info-subtle); }
.mobile-home__highlights strong { margin-top: auto; color: var(--text-strong); font-size: 14px; }
.mobile-home__highlights small { color: var(--text-muted); line-height: 1.3; }
.mobile-home__group { display: flex; flex-direction: column; gap: 10px; animation: soft-pop var(--motion-slow) var(--motion-spring) both; }
.mobile-home__group:nth-of-type(3) { animation-delay: 70ms; }
.mobile-home__group:nth-of-type(4) { animation-delay: 120ms; }
.mobile-home__group:nth-of-type(5) { animation-delay: 170ms; }
.mobile-home__group-head { display: flex; align-items: end; justify-content: space-between; }
.mobile-home__group-head h2 { margin: 0; color: var(--text-strong); font-size: 15px; }
.mobile-home__group-head span { color: var(--text-muted); font-size: 10px; }
.mobile-home__links { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--border); border-radius: 18px; background: var(--surface-card); }
.mobile-home__links button { min-width: 0; height: 58px; padding: 0 14px; display: grid; grid-template-columns: 34px 1fr auto; align-items: center; gap: 9px; border: 0; border-bottom: 1px solid var(--border-subtle); background: transparent; color: var(--text-muted); text-align: left; cursor: pointer; }
.mobile-home__links button:hover { background: var(--surface-hover); padding-left: 17px; }
.mobile-home__links button:nth-child(odd) { border-right: 1px solid var(--border-subtle); }
.mobile-home__links button strong { overflow: hidden; color: var(--text-body); font-size: 12.5px; text-overflow: ellipsis; white-space: nowrap; }
.mobile-home__links button > span { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 10px; background: var(--surface-sunken); color: var(--text-brand); }

@media (max-width: 620px) {
  .mobile-home__highlights { grid-template-columns: repeat(2, 1fr); }
  .mobile-home__highlights > button { min-height: 122px; }
  .mobile-home__links { grid-template-columns: 1fr; }
  .mobile-home__links button:nth-child(odd) { border-right: 0; }
}
</style>
