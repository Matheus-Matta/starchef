<template>
  <Card
    :title="title"
    subtitle="Área pronta para conectar nos endpoints do backend."
    :body-style="{ minHeight: '320px', display: 'grid', placeItems: 'center' }"
  >
    <div class="placeholder-panel">
      <span class="placeholder-panel__tag">{{ view }}</span>
      <h2>{{ title }}</h2>
      <p>Estrutura visual convertida para Vue. Agora dá para plugar dados reais sem mexer no design system.</p>
    </div>
  </Card>
</template>

<script setup>
import Card from "../components/display/Card.vue";

defineProps({
  title: { type: String, required: true },
  view: { type: String, required: true },
});
</script>

<style scoped>
.placeholder-panel {
  text-align: center;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.placeholder-panel__tag {
  height: 24px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-pill);
  background: var(--brand-subtle);
  color: var(--text-brand);
  font: var(--weight-bold) 11px/1 var(--font-mono);
  text-transform: uppercase;
}

.placeholder-panel h2 {
  font: var(--weight-extra) var(--text-3xl) / 1.1 var(--font-sans);
  color: var(--text-strong);
}

.placeholder-panel p {
  font: var(--weight-medium) 14px/1.6 var(--font-sans);
  color: var(--text-muted);
}
</style>
