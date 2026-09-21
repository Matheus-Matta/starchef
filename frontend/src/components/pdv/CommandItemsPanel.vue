<template>
  <section class="painel" :aria-label="titulo">
    <header class="painel__topo">
      <div>
        <h2 class="pdv-page__title painel__titulo">{{ titulo }}</h2>
        <p v-if="subtitulo" class="pdv-page__subtitle">{{ subtitulo }}</p>
      </div>
      <span v-if="emFechamento" class="pdv-badge">em fechamento</span>
    </header>

    <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>

    <nav class="pdv-tabs">
      <button
        type="button"
        :class="['pdv-tab', { 'pdv-tab--active': !historico }]"
        @click="trocar(false)"
      >
        O que tem agora
      </button>
      <!-- A segunda aba é o que sobrevive à venda: nada é apagado quando a
           comanda é paga, só marcado como fechado. -->
      <button
        type="button"
        :class="['pdv-tab', { 'pdv-tab--active': historico }]"
        @click="trocar(true)"
      >
        Histórico do cartão
      </button>
    </nav>

    <div class="pdv-scroll painel__lista">
      <p v-if="carregando" class="pdv-empty">Carregando…</p>
      <p v-else-if="!itens.length" class="pdv-empty">
        {{ historico ? "Este cartão nunca foi usado." : "Nenhum item aberto nesta comanda." }}
      </p>
      <ul v-else class="painel__itens">
        <CommandItemRow
          v-for="item in itens"
          :key="item.id"
          :item="item"
          :mostrar-estado="historico"
        />
      </ul>
    </div>

    <footer class="painel__rodape">
      <p class="painel__total">
        <span>{{ historico ? "Total do histórico" : "Total aberto" }}</span>
        <strong class="pdv-num">{{ dinheiro(total) }}</strong>
      </p>
      <button
        class="pdv-btn pdv-btn--primary"
        type="button"
        :disabled="carregando || imprimindo || !itens.length"
        @click="imprimir"
      >
        {{ imprimindo ? "Enviando…" : "Imprimir conferência" }}
      </button>
      <p class="pdv-muted painel__aviso">
        Conferência não é documento fiscal — a NFC-e sai no pagamento.
      </p>
    </footer>
  </section>
</template>

<script setup>
/**
 * O painel de UMA comanda: o que ela tem, e o que ela já teve.
 *
 * É um painel de página, não um diálogo — a página `/pdv/comandas` já traz o
 * cabeçalho, o trilho e a barra de estado do PDV, e repetir essa moldura aqui
 * dentro daria duas bordas para a mesma coisa.
 *
 * A consulta vive em `useCommandItems`: ela responde a uma pergunta de
 * DOMÍNIO ("o que tem agora" × "o que já teve"), e o componente cuida só de
 * mostrar. Ver o composable para o porquê de as duas abas serem consultas
 * separadas, e não um filtro sobre a mesma lista.
 */
import { computed, toRef } from "vue";

import CommandItemRow from "./CommandItemRow.vue";
import { useCommandItems } from "../../composables/useCommandItems";

const props = defineProps({
  command: { type: Object, required: true },
});

const emit = defineEmits(["printed"]);

const {
  itens,
  carregando,
  imprimindo,
  historico,
  erro,
  emFechamento,
  total,
  trocarAba: trocar,
  imprimir: enviarConferencia,
} = useCommandItems(toRef(props, "command"));

const titulo = computed(() => `Comanda ${props.command?.number ?? ""}`);
const subtitulo = computed(() =>
  [props.command?.code, props.command?.customer_name].filter(Boolean).join(" · "),
);

async function imprimir() {
  if (await enviarConferencia()) emit("printed");
}

function dinheiro(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
</script>

<style scoped>
/* Só o que é DESTE painel: a moldura e a pilha. O vocabulário visual
   (avisos, abas, item, selo) vive em `styles/pdv-panels.css`. */
.painel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  height: 100%;
  padding: 14px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 10px;
  background: var(--surface-card, #fff);
  box-sizing: border-box;
}

.painel__topo {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.painel__titulo {
  font-size: 18px;
}

.painel__lista {
  flex: 1;
}

.painel__itens {
  list-style: none;
  margin: 0;
  padding: 0;
}

.painel__rodape {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--surface-border, #e5e7eb);
}

.painel__total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin: 0;
  font-size: 14px;
}

.painel__total strong {
  font-size: 20px;
}

.painel__aviso {
  margin: 0;
  text-align: center;
}
</style>
