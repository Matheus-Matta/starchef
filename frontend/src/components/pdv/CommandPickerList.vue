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
        <!-- "Em fechamento" é DERIVADO do backend (`closing_merge`), nunca um
             estado gravado na comanda: um terceiro estado no banco seria mais
             uma coisa a sincronizar e a divergir. -->
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

/**
 * O estado da comanda, na ordem que importa.
 *
 * "Em fechamento" vem ANTES de "ocupada": as duas são verdade ao mesmo tempo,
 * e a que muda o que o operador pode fazer é a primeira — um cartão que o
 * caixa está cobrando não aceita lançamento.
 */
function estado(comanda) {
  if (comanda.closing_merge) return "fechamento";
  return comanda.status === "occupied" ? "ocupada" : "livre";
}

function rotulo(comanda) {
  return { fechamento: "em fechamento", ocupada: "ocupada", livre: "livre" }[
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
