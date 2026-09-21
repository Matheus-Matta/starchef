<template>
  <div class="pdv-scroll lista">
    <p v-if="carregando && !comandas.length" class="pdv-empty">Carregando…</p>
    <p v-else-if="!comandas.length" class="pdv-empty">{{ vazio }}</p>
    <button
      v-for="comanda in comandas"
      :key="comanda.id"
      type="button"
      class="pdv-card"
      :class="{ 'pdv-card--active': selecionadaId === comanda.id }"
      @click="$emit('pick', comanda)"
    >
      <span class="pdv-card__top">
        <strong>{{ comanda.number }}</strong>
        <span class="pdv-badge" :class="`pdv-badge--${estado(comanda)}`">
          {{ rotulo(comanda) }}
        </span>
      </span>
      <span class="pdv-card__meta">
        <small>{{ comanda.code }}</small>
        <small>{{ comanda.customer_name || "—" }}</small>
      </span>
    </button>
  </div>
</template>

<script setup>
/** A lista de cartões da página de comandas. */
defineProps({
  comandas: { type: Array, default: () => [] },
  selecionadaId: { type: [String, Number], default: null },
  carregando: { type: Boolean, default: false },
  vazio: { type: String, default: "Nenhuma comanda encontrada." },
});

defineEmits(["pick"]);

/** Ocupada é ter anotação PENDENTE — o backend mantém esse retrato. */
function estado(comanda) {
  return comanda.status === "occupied" ? "ocupada" : "livre";
}

function rotulo(comanda) {
  return { ocupada: "ocupada", livre: "livre" }[
    estado(comanda)
  ];
}
</script>

<style scoped>
.lista {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
