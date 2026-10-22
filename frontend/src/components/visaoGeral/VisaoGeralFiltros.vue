<template>
  <div class="vg-filtros">
    <p class="vg-filtros__sub">{{ subtitulo }}</p>
    <div class="vg-filtros__controles">
      <label v-if="podeEscolherRestaurante" class="vg-filtros__restaurante">
        <span>Restaurante</span>
        <select :value="restaurante" aria-label="Restaurante" @change="$emit('update:restaurante', $event.target.value)">
          <option value="">Todos os restaurantes</option>
          <option v-for="opcao in restaurantes" :key="opcao.value" :value="opcao.value">{{ opcao.label }}</option>
        </select>
      </label>
      <SelectButton
        :model-value="periodo"
        :options="periodos"
        option-label="label"
        option-value="value"
        :allow-empty="false"
        aria-label="Período"
        @update:model-value="$emit('update:periodo', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import SelectButton from "primevue/selectbutton";

import { PERIODOS } from "../../composables/useVisaoGeral";

const props = defineProps({
  periodo: { type: String, required: true },
  restaurante: { type: String, default: "" },
  restaurantes: { type: Array, default: () => [] },
  podeEscolherRestaurante: { type: Boolean, default: false },
  intervalo: { type: Object, default: null },
});
defineEmits(["update:periodo", "update:restaurante"]);

const periodos = PERIODOS;

function data(iso) {
  if (!iso) return "";
  const [ano, mes, dia] = String(iso).split("-");
  return `${dia}/${mes}/${ano}`;
}

const subtitulo = computed(() => {
  const { de, ate } = props.intervalo || {};
  if (!de) return "Hoje";
  if (props.periodo === "dia" || de === ate) return `Hoje, ${data(de)}`;
  return `De ${data(de)} até hoje`;
});
</script>

<style scoped>
.vg-filtros { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px; }
.vg-filtros__sub { margin: 0; color: var(--text-strong); font: var(--weight-semibold) 15px/1.2 var(--font-sans); }
.vg-filtros__controles { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; }
.vg-filtros__restaurante { display: flex; flex-direction: column; gap: 4px; min-width: 200px; }
.vg-filtros__restaurante span {
  color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans);
  text-transform: uppercase; letter-spacing: var(--tracking-caps);
}
.vg-filtros__restaurante select {
  height: var(--control-h); padding: 0 28px 0 10px; border: 1px solid var(--border); border-radius: 4px;
  background: var(--surface-card); color: var(--text-body); font: var(--weight-medium) 13px/1 var(--font-sans);
}
@media (max-width: 720px) {
  .vg-filtros__controles, .vg-filtros__restaurante { width: 100%; }
}
</style>
