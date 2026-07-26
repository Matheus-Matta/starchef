<template>
  <nav class="mobile-bottom-nav" aria-label="Navegação principal">
    <button type="button" :class="{ 'is-active': active === 'painel' }" @click="$emit('navigate', 'painel')">
      <AppIcon name="home" :size="20" />
      <span>Home</span>
    </button>
    <button type="button" :class="{ 'is-active': active === 'pedidos' }" @click="$emit('navigate', 'pedidos')">
      <AppIcon name="receipt-text" :size="20" />
      <span>Pedidos</span>
    </button>
    <button class="mobile-bottom-nav__create" type="button" :disabled="!canCreate" :aria-label="createLabel" @click="$emit('create')">
      <AppIcon name="plus" :size="25" />
      <span>{{ createLabel }}</span>
    </button>
    <button type="button" :class="{ 'is-active': active === 'pdv' }" @click="$emit('navigate', 'pdv')">
      <AppIcon name="shopping-cart" :size="20" />
      <span>PDV</span>
    </button>
    <button type="button" :aria-expanded="menuOpen" @click="$emit('menu')">
      <AppIcon name="panel-left" :size="20" />
      <span>Menu</span>
    </button>
  </nav>
</template>

<script setup>
import AppIcon from "./AppIcon.vue";

defineProps({
  active: { type: String, default: "painel" },
  canCreate: { type: Boolean, default: false },
  createLabel: { type: String, default: "Criar" },
  menuOpen: { type: Boolean, default: false },
});

defineEmits(["navigate", "create", "menu"]);
</script>

<style scoped>
.mobile-bottom-nav { display: none; }

@media (max-width: 900px) {
  .mobile-bottom-nav {
    position: fixed;
    left: 10px;
    right: 10px;
    bottom: max(6px, env(safe-area-inset-bottom));
    z-index: 45;
    height: 58px;
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    align-items: center;
    padding: 3px 7px;
    background: color-mix(in srgb, var(--surface-card) 94%, transparent);
    border: 1px solid var(--border);
    border-radius: 20px;
    box-shadow: 0 12px 34px rgba(15, 23, 42, .18);
    backdrop-filter: blur(18px);
  }

  .mobile-bottom-nav button {
    min-width: 0;
    height: 46px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border: 0;
    background: transparent;
    color: var(--text-muted);
    font: var(--weight-bold) 10.5px/1 var(--font-sans);
  }

  .mobile-bottom-nav button.is-active { color: var(--text-strong); }
  .mobile-bottom-nav button:not(.mobile-bottom-nav__create) :deep(i) { font-size: 20px !important; }
  .mobile-bottom-nav button:not(.mobile-bottom-nav__create) > span { padding-top: 6px; }

  .mobile-bottom-nav__create {
    width: 42px;
    height: 42px !important;
    justify-self: center;
    transform: translateY(-9px);
    border-radius: 50% !important;
    background: var(--text-strong) !important;
    color: var(--surface-card) !important;
    box-shadow: 0 8px 20px rgba(15, 23, 42, .28);
  }
  .mobile-bottom-nav__create :deep(i) { font-size: 22px !important; }

  .mobile-bottom-nav__create span {
    position: absolute;
    top: calc(100% + 4px);
    font-size: 9.5px;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .mobile-bottom-nav__create:disabled {
    opacity: .32;
    box-shadow: none;
  }
}
</style>
