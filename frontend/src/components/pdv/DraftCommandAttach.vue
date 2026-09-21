<template>
  <div class="anexo">
    <!-- Sem comanda o pedido é de BALCÃO, e isso precisa estar dito: é a
         diferença entre o cliente levar o cupom agora e a conta ficar num
         cartão até ele sair. -->
    <!-- Um cartão por linha: a mesa que paga junto é o caso, não a exceção,
         e o cliente confere em voz alta "quanto é a minha?". -->
    <!-- Um cartão por linha: a mesa que paga junto é o caso, não a exceção,
         e o cliente confere em voz alta "quanto é a minha?". -->
    <DraftAttachedCommand
      v-for="atual in comandas"
      :key="atual.id"
      :comanda="atual"
      :disabled="disabled"
      @detach="$emit('detach', atual.id)"
    />

    <button class="anexo__botao" type="button" :disabled="disabled" @click="abrir = true">
      <span class="anexo__rotulo">{{ comandas.length ? "" : "Balcão" }}</span>
      <span class="anexo__acao">
        {{ comandas.length ? "Incluir outra comanda" : "Incluir comanda" }}
      </span>
    </button>

    <div v-if="abrir" class="anexo__seletor">
      <CommandScannerInput
        :disabled="carregando"
        hint="Passe o cartão ou escolha na lista."
        @scan="escolherPorCodigo"
      />
      <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>
      <CommandPickerList
        :comandas="disponiveis"
        :carregando="carregando"
        vazio="Nenhuma comanda livre."
        @pick="escolher"
      />
      <button class="pdv-btn pdv-btn--ghost anexo__cancelar" type="button" @click="abrir = false">
        Cancelar
      </button>
    </div>
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
 */
import { computed, ref, watch } from "vue";

import CommandPickerList from "./CommandPickerList.vue";
import CommandScannerInput from "./CommandScannerInput.vue";
import DraftAttachedCommand from "./DraftAttachedCommand.vue";
import { api } from "../../services/api";
import { findCommandByCode } from "../../services/commandService";

defineProps({
  comandas: { type: Array, default: () => [] },
  mesa: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["attach", "detach"]);

const abrir = ref(false);
const disponiveisNoServidor = ref([]);
const carregando = ref(false);
const erro = ref("");

/** Comanda em fechamento não entra: o caixa está cobrando aquele cartão. */
const disponiveis = computed(() =>
  // Cartão sem valor não entra: ele não acrescenta um centavo à conta, e
  // anexá-lo só prende um pedido a um cartão que não cobra nada.
  disponiveisNoServidor.value.filter((item) => Number(item.pending_total || 0) > 0),
);

async function carregar() {
  carregando.value = true;
  erro.value = "";
  try {
    const { data } = await api.get("/commands/", {
      params: { page_size: 200, is_active: true },
    });
    disponiveisNoServidor.value = data?.results || data || [];
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || "Não foi possível listar as comandas.";
  } finally {
    carregando.value = false;
  }
}

async function escolherPorCodigo(codigo) {
  carregando.value = true;
  erro.value = "";
  try {
    escolher(await findCommandByCode(codigo));
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || `Comanda "${codigo}" não encontrada.`;
  } finally {
    carregando.value = false;
  }
}

function escolher(comanda) {
  if (comanda?.closing_merge) {
    erro.value = `A comanda ${comanda.number} está em fechamento no caixa.`;
    return;
  }
  abrir.value = false;
  emit("attach", comanda);
}

watch(abrir, (aberto) => {
  if (aberto) carregar();
});
</script>

<style scoped>
.anexo {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.anexo__botao,
.anexo__atual {
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

.anexo__atual {
  border-style: solid;
  cursor: default;
}

.anexo__rotulo {
  font-size: 13px;
}

.anexo__mesa {
  margin-left: 6px;
  font-style: normal;
  font-size: 11px;
  color: var(--text-color-secondary, #6b7280);
}

.anexo__acao {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color, #2563eb);
}

.anexo__soltar {
  border: 0;
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}

.anexo__seletor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 340px;
  padding: 10px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: var(--surface-card, #fff);
}

.anexo__cancelar {
  align-self: flex-end;
}
</style>
