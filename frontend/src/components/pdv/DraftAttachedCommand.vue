<template>
  <div class="anexo__atual">
    <span class="anexo__rotulo">
      Comanda <strong>{{ comanda.number }}</strong>
      <em v-if="comanda.pending_total" class="anexo__mesa">
        {{ dinheiro(comanda.pending_total) }}
      </em>
    </span>
    <button class="anexo__soltar" type="button" :disabled="disabled" @click="$emit('detach')">
      Retirar
    </button>
  </div>
</template>

<script setup>
/**
 * Um cartão anexado ao rascunho, com o que ele tem a cobrar.
 *
 * O valor fica AQUI, ao lado do número, porque é o que o cliente confere em
 * voz alta antes de pagar: numa conta com quatro cartões, "quanto é a minha?"
 * é a primeira pergunta.
 */
defineProps({
  comanda: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
});

defineEmits(["detach"]);

function dinheiro(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}
</script>

<style scoped>
/* A moldura e as medidas vêm do pai (`DraftCommandAttach`): estas classes são
   do vocabulário dele, e repetir o estilo aqui faria as duas cópias divergirem
   no primeiro ajuste de altura. */
</style>
