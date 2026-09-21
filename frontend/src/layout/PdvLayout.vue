<template>
  <div class="pdv-shell" :data-theme="theme">
    <PdvNavigationRail
      :active="activeDestination"
      :show-orders="canViewOrders"
      :show-finance="canAccessCash"
      :show-merge="canMergeCommands"
      :show-commands="canViewCommands"
      @navigate="goTo"
      @exit="leavePdv"
    />

    <div class="pdv-shell__main">
      <PdvOperationalBar
        :cash-name="cashName"
        :operator-name="operatorName"
        :shift-label="shiftLabel"
        :cash-open="cashOpen"
        :online="browserOnline"
        :theme="theme"
        @toggle-theme="toggleTheme"
      />

      <section class="pdv-shell__content">
        <RouterView />
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * Casca do PDV na web: tela cheia, sem barra lateral de retaguarda e sem
 * cabeçalho do painel.
 *
 * O layout espelha o do aplicativo desktop de propósito — trilho estreito à
 * esquerda, barra de estado no topo, resto da tela para a venda. Quem opera o
 * caixa alterna entre os dois durante o turno, e duas telas com a mesma função
 * em lugares diferentes obriga a pessoa a reaprender no meio do movimento.
 *
 * Referência: `pdv_desktop/lib/features/home/presentation/pdv_navigation_rail.dart`
 * e `pdv_operational_chrome.dart`.
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";

import PdvNavigationRail from "./pdv/PdvNavigationRail.vue";
import PdvOperationalBar from "./pdv/PdvOperationalBar.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const theme = ref(localStorage.getItem("starchef-theme") || "light");
const browserOnline = ref(navigator.onLine);

// O navegador é a única fonte de "tem rede" aqui. O desktop tem muito mais
// (agente local, impressora, fila), e a barra web mostra só o que sabe — um
// indicador que finge saber é pior que um indicador a menos.
function onOnline() {
  browserOnline.value = true;
}
function onOffline() {
  browserOnline.value = false;
}

onMounted(() => {
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
});
onUnmounted(() => {
  window.removeEventListener("online", onOnline);
  window.removeEventListener("offline", onOffline);
});

const operatorName = computed(() => {
  const user = auth.user || {};
  return (user.name || "").trim() || user.username || "Operador";
});

// Sem sessão de caixa carregada nesta casca, o rótulo é o nome do posto. A
// tela de venda é quem conhece a sessão; duplicar essa busca aqui daria dois
// pedidos para a mesma resposta e duas verdades quando uma delas atrasasse.
const cashName = computed(() => auth.user?.restaurant_name || "StarChef PDV");
const cashOpen = computed(() => Boolean(auth.pdvCashOpen));
const shiftLabel = computed(() => (cashOpen.value ? "Turno em andamento" : "Turno não iniciado"));

const canViewOrders = computed(() => auth.hasPermission("orders.view") || auth.hasPermission("orders.view.own"));
const canAccessCash = computed(() => auth.hasPermission("cash.view.own") || auth.hasPermission("cash.view"));
const canMergeCommands = computed(() => auth.hasPermission("orders.merge"));
const canViewCommands = computed(() => auth.hasPermission("tables.view"));

const activeDestination = computed(() => route.meta.pdvNav || "venda");

function goTo(destination) {
  const alvo = {
    venda: { name: "pdv-venda" },
    comandas: { name: "pdv-comandas" },
    "conta-agrupada": { name: "pdv-conta-agrupada" },
    pedidos: { name: "pedidos" },
    mesas: { name: "mesas" },
    caixa: { name: "caixa" },
  }[destination];
  if (alvo) router.push(alvo);
}

/** Sair do PDV devolve para a retaguarda, que é onde o menu completo vive. */
function leavePdv() {
  router.push({ name: "painel" });
}

function toggleTheme() {
  theme.value = theme.value === "light" ? "dark" : "light";
  localStorage.setItem("starchef-theme", theme.value);
}
</script>

<style scoped>
.pdv-shell {
  display: flex;
  height: 100vh;
  height: 100dvh;
  width: 100%;
  overflow: hidden;
  background: var(--surface-ground, #f6f7f9);
  color: var(--text-color, #111827);
}

.pdv-shell__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

/* `min-height: 0` é o que permite o conteúdo rolar dentro do flex em vez de
   esticar a casca e tirar a barra de estado da tela. */
.pdv-shell__content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
