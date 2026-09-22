<template>
  <div class="anexo">
    <!-- Sem comanda o pedido é de BALCÃO, e isso precisa estar dito: é a
         diferença entre o cliente levar o cupom agora e a conta ficar num
         cartão até ele sair. -->
    <button class="anexo__botao" type="button" :disabled="disabled" @click="abrir = true">
      <span class="anexo__rotulo">{{ rotulo }}</span>
      <span class="anexo__acao">
        {{ comandas.length ? "Incluir outra comanda" : "Incluir comanda" }}
      </span>
    </button>

    <CommandAttachPicker
      v-if="abrir"
      :comandas="comandas"
      :disabled="disabled"
      @attach="anexar"
      @detach="$emit('detach', $event)"
      @close="abrir = false"
    />
  </div>
</template>

<script setup>
/**
 * Anexar uma comanda ao rascunho — sem criar pedido nenhum.
 *
 * É a diferença que este controle existe para fazer: escolher a comanda 13
 * aqui **não abre pedido**. Antes, a escolha disparava `open-command` na hora,
 * e desistir deixava o cartão ocupado com um pedido vazio que alguém tinha de
 * ir cancelar depois.
 *
 * A comanda vira um atributo do carrinho, do mesmo jeito que o cliente. O
 * pedido nasce quando a cozinha ou o caixa precisam dele.
 *
 * Aqui mora só o botão e o estado de aberto; a busca no servidor, a leitura
 * do cartão e a regra de quem pode entrar vivem no `CommandAttachPicker`.
 */
import { computed, ref } from "vue";

import CommandAttachPicker from "./CommandAttachPicker.vue";

const props = defineProps({
  comandas: { type: Array, default: () => [] },
  mesa: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["attach", "detach"]);

const abrir = ref(false);

const rotulo = computed(() => {
  const quantas = props.comandas.length;
  if (!quantas) return "Balcão";
  return `${quantas} comanda${quantas > 1 ? "s" : ""}`;
});

function anexar(comanda) {
  // O modal FICA aberto: a mesa que paga junto é o caso, não a exceção, e
  // fechar a cada cartão obrigaria a reabrir quatro vezes.
  emit("attach", comanda);
}
</script>

<style scoped>
.anexo {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.anexo__botao {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border: 1px dashed var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.anexo__rotulo {
  font-size: 13px;
}

.anexo__acao {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color, #2563eb);
}
</style>
