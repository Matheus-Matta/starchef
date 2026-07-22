<template>
  <header v-if="hasContent" class="apphead">
    <div class="apphead__lead">
      <nav v-if="breadcrumbs.length" class="apphead__crumbs" aria-label="Trilha de navegação">
        <template v-for="(crumb, index) in breadcrumbs" :key="index">
          <button v-if="crumb.to" type="button" class="apphead__crumb apphead__crumb--link" @click="$emit('navigate', crumb)">
            {{ crumb.label }}
          </button>
          <span v-else class="apphead__crumb">{{ crumb.label }}</span>
          <AppIcon v-if="index < breadcrumbs.length - 1" name="chevron-right" :size="11" class="apphead__crumb-sep" />
        </template>
      </nav>

      <div v-if="title || subtitle" class="apphead__title-wrap">
        <h1 v-if="title" class="apphead__title">{{ title }}</h1>
        <p v-if="subtitle" class="apphead__subtitle">{{ subtitle }}</p>
      </div>
    </div>

    <div v-if="$slots.actions" class="apphead__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
/**
 * Cabeçalho de página único: título, breadcrumb e ações (Sprint 0 · STC-004).
 * Evita títulos duplicados — a página só renderiza este componente quando há
 * conteúdo próprio a mostrar (título, trilha ou ações).
 */
import { computed, useSlots } from "vue";
import AppIcon from "../AppIcon.vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  /** Trilha: [{ label, to? }] — `to` opcional emite 'navigate'. */
  breadcrumbs: { type: Array, default: () => [] },
});

defineEmits(["navigate"]);

const slots = useSlots();
const hasContent = computed(
  () => Boolean(props.title || props.subtitle || props.breadcrumbs.length || slots.actions),
);
</script>

<style scoped>
.apphead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}
.apphead__lead { display: flex; flex-direction: column; gap: 6px; min-width: 0; }

.apphead__crumbs { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.apphead__crumb { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.apphead__crumb--link { background: none; border: none; padding: 0; cursor: pointer; color: var(--text-muted); }
.apphead__crumb--link:hover { color: var(--text-body); text-decoration: underline; }
.apphead__crumb:last-of-type { color: var(--text-strong); }
.apphead__crumb-sep { color: var(--text-subtle); }

.apphead__title { color: var(--text-strong); font: var(--weight-extra) 20px/1.2 var(--font-sans); }
.apphead__subtitle { color: var(--text-muted); font: var(--weight-medium) 13px/1.4 var(--font-sans); }

.apphead__actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
</style>
