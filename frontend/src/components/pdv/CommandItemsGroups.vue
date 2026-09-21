<template>
  <div>
    <!-- O que está ABERTO vem primeiro e nunca se mistura com o que já foi:
         é o único grupo que vira dinheiro. Um cartão reutilizado mostra este
         vazio e o histórico do cliente anterior abaixo, marcado como passado. -->
    <h3 class="grupo">Nesta conta ({{ pendentes.length }})</h3>
    <p v-if="!pendentes.length" class="pdv-empty grupo__vazio">
      Nada aberto nesta comanda.
    </p>
    <ul v-else class="itens">
      <CommandItemRow v-for="item in pendentes" :key="item.id" :item="item" />
    </ul>

    <h3 v-if="fechados.length" class="grupo">
      Já passaram por aqui ({{ fechados.length }})
    </h3>
    <ul v-if="fechados.length" class="itens itens--passado">
      <CommandItemRow
        v-for="item in fechados"
        :key="item.id"
        :item="item"
        mostrar-estado
      />
    </ul>
  </div>
</template>

<script setup>
/**
 * O cartão inteiro, em dois grupos: o que está aberto e o que já passou.
 *
 * Eram duas abas, e quem abria a comanda via só a primeira. A pergunta do
 * operador é a mesma nas duas — *o que passou por aqui?* —, e é conferindo o
 * que já foi que ele resolve uma reclamação de conta ou descobre que o item
 * foi cancelado, não sumiu.
 *
 * A separação em grupos não é enfeite: ela é o que protege o cartão
 * reutilizado de reaparecer com a conta do cliente anterior.
 */
import CommandItemRow from "./CommandItemRow.vue";

defineProps({
  /** O que entra na próxima conta. */
  pendentes: { type: Array, required: true },
  /** O que já foi cobrado ou cancelado — não entra em conta nenhuma. */
  fechados: { type: Array, required: true },
});
</script>

<style scoped>
.itens {
  list-style: none;
  margin: 0;
  padding: 0;
}

/* O que já foi some um pouco: continua legível para conferência, sem competir
   com o que ainda vai ser cobrado. */
.itens--passado {
  opacity: 0.7;
}

.grupo {
  margin: 14px 0 6px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-color-secondary, #6b7280);
}

.grupo:first-child {
  margin-top: 0;
}

.grupo__vazio {
  margin: 0 0 4px;
}
</style>
