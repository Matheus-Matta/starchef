<template>
  <div class="cupom">
    <div
      v-if="applied"
      class="cupom__aplicado"
      :aria-label="`Cupom ${applied} abatendo ${money(discount)}`"
    >
      <span class="cupom__aplicado-nome"><i class="pi pi-ticket" /> {{ applied }}</span>
      <strong class="cupom__aplicado-valor">- {{ money(discount) }}</strong>
    </div>

    <div class="cupom__linha">
      <input
        v-model="codigo"
        class="cupom__input"
        type="text"
        maxlength="40"
        autocomplete="off"
        placeholder="Cupom de desconto"
        aria-label="Código do cupom de desconto"
        :disabled="ocupado || disabled"
        :aria-invalid="Boolean(erro)"
        @input="codigo = codigo.toUpperCase()"
        @keyup.enter="aplicar"
      />
      <button
        v-if="!applied"
        class="cupom__btn cupom__btn--aplicar"
        type="button"
        :disabled="ocupado || disabled || !codigo.trim()"
        @click="aplicar"
      >
        {{ ocupado ? "Validando..." : "Aplicar" }}
      </button>
      <template v-else>
        <button
          class="cupom__btn cupom__btn--aplicar"
          type="button"
          :disabled="ocupado || disabled || !codigo.trim()"
          @click="aplicar"
        >
          Trocar
        </button>
        <button
          class="cupom__btn cupom__btn--retirar"
          type="button"
          :disabled="ocupado || disabled"
          @click="retirar"
        >
          Retirar
        </button>
      </template>
    </div>

    <small v-if="erro" class="cupom__erro">{{ erro }}</small>
  </div>
</template>

<script setup>
/**
 * Cupom de desconto no PDV web: aplicar, trocar e retirar.
 *
 * QUEM VALIDA É O SERVIDOR, sempre. O navegador não sabe se este CPF já usou o
 * cupom, se o mínimo em produtos foi alcançado ou se ele venceu há uma hora — e
 * uma validação otimista aqui mostraria o desconto na tela para o servidor
 * recusar depois, com o cliente já tendo ouvido o valor menor.
 *
 * A ROTA É A MESMA para os três gestos (`apply-coupon`, com `code` vazio
 * retirando). Uma rota por gesto faria este componente escolher qual chamar a
 * partir de um campo de texto, e escolher errado em silêncio.
 *
 * O componente não guarda o total: ele emite o pedido que o servidor devolveu,
 * já recalculado. É de lá que a tela tira o restante e o troco — refazer a
 * conta no navegador faria a tela mostrar um número e a venda cobrar outro.
 */
import { ref, watch } from "vue";

import { api } from "../../services/api";
import { formatMoney } from "../../utils/format";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({
  orderId: { type: String, required: true },
  /** O código que o pedido já carrega, vazio quando não há cupom. */
  applied: { type: String, default: "" },
  /** Quanto o cupom aplicado está abatendo agora. */
  discount: { type: [Number, String], default: 0 },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["applied"]);

const codigo = ref(props.applied || "");
const erro = ref("");
const ocupado = ref(false);

// O campo acompanha o pedido: um `refreshCart` que traga cupom diferente (o
// recálculo pode ter derrubado o que estava aplicado) precisa aparecer aqui, ou
// o operador leria um código que já não vale.
watch(
  () => props.applied,
  (valor) => {
    codigo.value = valor || "";
  },
);

const money = (valor) => formatMoney(valor);

async function enviar(code) {
  if (ocupado.value) return;
  ocupado.value = true;
  erro.value = "";
  try {
    const { data } = await api.post(`/orders/${props.orderId}/apply-coupon/`, { code });
    emit("applied", data);
  } catch (falha) {
    // A recusa fica NO CAMPO, e não num toast: a frase do servidor é sobre o
    // cupom ("Este CPF já usou este cupom") e quem precisa lê-la está olhando o
    // campo que acabou de digitar.
    erro.value = normalizeApiError(falha).message || "Não foi possível aplicar o cupom.";
  } finally {
    ocupado.value = false;
  }
}

const aplicar = () => enviar(codigo.value.trim());

function retirar() {
  codigo.value = "";
  return enviar("");
}
</script>

<style scoped src="./PdvCouponField.css"></style>
