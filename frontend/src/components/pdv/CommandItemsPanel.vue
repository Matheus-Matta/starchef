<template>
  <section class="painel" :aria-label="titulo">
    <header class="painel__topo">
      <div>
        <h2 class="pdv-page__title painel__titulo">{{ titulo }}</h2>
        <p v-if="subtitulo" class="pdv-page__subtitle">{{ subtitulo }}</p>
      </div>
    </header>

    <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>

    <!-- ONDE O CARTÃO ESTÁ SENTADO. Quem está olhando a comanda é quem sabe
         para qual mesa ela foi; antes isso só existia no meio do fluxo de
         abrir pedido, e um cartão na mesa errada só era corrigido ao cobrar. -->
    <CommandTableLink
      :comanda="command"
      :restaurant-id="restaurantId"
      @changed="$emit('table-changed')"
    />

    <div class="pdv-scroll painel__lista">
      <p v-if="carregando" class="pdv-empty">Carregando…</p>
      <p v-else-if="!itens.length" class="pdv-empty">Este cartão nunca foi usado.</p>
      <CommandItemsGroups v-else :pendentes="pendentes" :fechados="fechados" />
    </div>

    <footer class="painel__rodape">
      <p class="painel__total">
        <span>Total aberto</span>
        <strong class="pdv-num">{{ dinheiro(total) }}</strong>
      </p>
      <!-- O histórico fica em letra menor de propósito: ele é conferência, e
           somá-lo ao aberto seria cobrar duas vezes o que já foi pago. -->
      <p v-if="fechados.length" class="pdv-muted painel__total painel__total--passado">
        <span>Já fechado neste cartão</span>
        <span class="pdv-num">{{ dinheiro(totalHistorico) }}</span>
      </p>
      <button
        class="pdv-btn pdv-btn--primary"
        type="button"
        :disabled="carregando || imprimindo || !pendentes.length"
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
 * Mostra o cartão INTEIRO: o que está aberto e o que já passou por ele. Eram
 * duas abas, e quem abria a comanda via só a primeira — mas a pergunta do
 * operador é a mesma nas duas, e é conferindo o que já foi que ele resolve
 * uma reclamação de conta ou descobre que o item foi cancelado, não sumiu.
 *
 * A consulta vive em `useCommandItems`; aqui só se desenha.
 */
import { computed, toRef } from "vue";

import CommandItemsGroups from "./CommandItemsGroups.vue";
import CommandTableLink from "./CommandTableLink.vue";
import { useCommandItems } from "../../composables/useCommandItems";

const props = defineProps({
  command: { type: Object, required: true },
  restaurantId: { type: [String, Number], default: null },
});

const emit = defineEmits(["printed", "table-changed"]);

const {
  itens,
  pendentes,
  fechados,
  carregando,
  imprimindo,
  erro,
  total,
  totalHistorico,
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
/* Só o que é DESTE painel: a moldura, o rodapé e os totais. Os grupos levaram
   o próprio CSS junto; o vocabulário visual (avisos, item, selo) vive em
   `styles/pdv-panels.css`. */
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


.painel__total--passado {
  font-size: 12px;
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
