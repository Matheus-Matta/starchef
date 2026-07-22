<template>
  <section class="appsection">
    <header v-if="title || $slots.actions" class="appsection__head">
      <div class="appsection__heading">
        <AppIcon v-if="icon" :name="icon" :size="15" class="appsection__icon" />
        <div>
          <h3 class="appsection__title">{{ title }}</h3>
          <p v-if="description" class="appsection__desc">{{ description }}</p>
        </div>
      </div>
      <div v-if="$slots.actions" class="appsection__actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="appsection__body">
      <slot />
    </div>
  </section>
</template>

<script setup>
/**
 * Seção de formulário com título opcional (Sprint 0 · STC-005).
 * Usada para agrupar campos relacionados (ex.: "Preços", "Disponibilidade")
 * mantendo espaçamento e tipografia consistentes entre telas.
 */
import AppIcon from "../AppIcon.vue";

defineProps({
  title: { type: String, default: "" },
  description: { type: String, default: "" },
  icon: { type: String, default: "" },
});
</script>

<style scoped>
.appsection { display: flex; flex-direction: column; gap: var(--space-3); }
.appsection + .appsection { margin-top: var(--section-gap); }

.appsection__head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}
.appsection__heading { display: flex; align-items: center; gap: 9px; min-width: 0; }
.appsection__icon { color: var(--text-muted); }
.appsection__title { color: var(--text-strong); font: var(--weight-extra) 14px/1.2 var(--font-sans); }
.appsection__desc { margin-top: 2px; color: var(--text-muted); font: var(--weight-medium) 12px/1.4 var(--font-sans); }
.appsection__actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.appsection__body { display: flex; flex-direction: column; gap: var(--space-3); }
</style>
