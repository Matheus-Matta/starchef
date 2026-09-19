<template>
  <nav class="pdv-rail" aria-label="Navegação do PDV">
    <button
      v-for="entry in entries"
      :key="entry.key"
      class="pdv-rail__item"
      :class="{ 'pdv-rail__item--active': entry.key === active }"
      type="button"
      :aria-current="entry.key === active ? 'page' : undefined"
      @click="$emit('navigate', entry.key)"
    >
      <i :class="entry.icon" />
      <span>{{ entry.label }}</span>
    </button>

    <div class="pdv-rail__spacer" />

    <button class="pdv-rail__item pdv-rail__item--exit" type="button" @click="$emit('exit')">
      <i class="pi pi-sign-out" />
      <span>Sair</span>
    </button>
  </nav>
</template>

<script setup>
/**
 * Trilho fixo do PDV, espelhando `pdv_navigation_rail.dart` do desktop.
 *
 * A largura nunca muda — nem ao passar o mouse, nem ao trocar de destino. É
 * regra herdada do desktop e a razão é operacional: o catálogo de produtos
 * não pode saltar de lugar enquanto alguém digita, porque o operador acerta o
 * botão de memória, sem olhar.
 */
import { computed } from "vue";

const props = defineProps({
  active: { type: String, default: "venda" },
  showOrders: { type: Boolean, default: true },
  showFinance: { type: Boolean, default: true },
});

defineEmits(["navigate", "exit"]);

const entries = computed(() => [
  { key: "venda", label: "Venda", icon: "pi pi-shopping-cart" },
  ...(props.showOrders ? [{ key: "pedidos", label: "Pedidos", icon: "pi pi-receipt" }] : []),
  { key: "mesas", label: "Mesas", icon: "pi pi-th-large" },
  ...(props.showFinance ? [{ key: "caixa", label: "Caixa", icon: "pi pi-wallet" }] : []),
]);
</script>

<style scoped>
.pdv-rail {
  width: 72px;
  flex: 0 0 72px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 8px 0;
  gap: 2px;
  background: var(--surface-card, #ffffff);
  border-right: 1px solid var(--surface-border, #e5e7eb);
}

.pdv-rail__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  /* Alvo de toque generoso: o PDV web roda em monitor com touch em boa parte
     das lojas, e 64px é o mínimo que se acerta sem mirar. */
  min-height: 64px;
  padding: 6px 2px;
  border: 0;
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
}

.pdv-rail__item i {
  font-size: 20px;
}

.pdv-rail__item:hover {
  background: var(--surface-hover, #f3f4f6);
  color: var(--text-color, #111827);
}

.pdv-rail__item--active {
  color: var(--primary-color, #2563eb);
  box-shadow: inset 3px 0 0 var(--primary-color, #2563eb);
}

.pdv-rail__item--exit {
  color: var(--text-color-secondary, #6b7280);
}

.pdv-rail__spacer {
  flex: 1;
}
</style>
