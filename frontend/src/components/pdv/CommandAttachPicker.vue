<template>
  <div class="seletor">
    <!-- O QUE JÁ ESTÁ NA CONTA vem primeiro, com o X ao lado.
         Antes ficava empilhado fora, acima do botão: numa mesa com quatro
         cartões o carrinho começava com quatro linhas antes do primeiro
         produto, e "incluir" ficava longe de "retirar". -->
    <div v-if="comandas.length" class="seletor__anexadas">
      <p class="seletor__titulo">Nesta conta</p>
      <DraftAttachedCommand
        v-for="atual in comandas"
        :key="atual.id"
        :comanda="atual"
        :disabled="disabled"
        @detach="$emit('detach', atual.id)"
      />
    </div>

    <CommandScannerInput
      :disabled="carregando"
      hint="Passe o cartão para incluir — ou de novo para retirar."
      @scan="porCodigo"
    />
    <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>
    <CommandPickerList
      :comandas="disponiveis"
      :carregando="carregando"
      vazio="Nenhuma comanda com valor a cobrar."
      @pick="$emit('attach', $event)"
    />
    <button class="pdv-btn pdv-btn--ghost seletor__fechar" type="button" @click="$emit('close')">
      Fechar
    </button>
  </div>
</template>

<script setup>
/**
 * O modal de incluir comanda: o que já está na conta e o que pode entrar.
 *
 * Separado do controle que o abre porque são dois assuntos — lá é um botão
 * com estado; aqui é a busca no servidor, a leitura do cartão e a regra de
 * qual cartão pode entrar.
 */
import { computed, onMounted, ref } from "vue";

import CommandPickerList from "./CommandPickerList.vue";
import CommandScannerInput from "./CommandScannerInput.vue";
import DraftAttachedCommand from "./DraftAttachedCommand.vue";
import { api } from "../../services/api";
import { findCommandByCode } from "../../services/commandService";

const props = defineProps({
  comandas: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["attach", "detach", "close"]);

const disponiveisNoServidor = ref([]);
const carregando = ref(false);
const erro = ref("");

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

/**
 * Ler o cartão ALTERNA: inclui se está fora, retira se já está na conta.
 *
 * É o mesmo gesto físico para os dois sentidos — o operador passa o cartão de
 * novo em vez de procurar um botão. Sem isso, ler duas vezes por engano não
 * fazia nada e ele ficava sem saber se a primeira leitura pegou.
 */
async function porCodigo(codigo) {
  carregando.value = true;
  erro.value = "";
  try {
    const comanda = await findCommandByCode(codigo);
    const jaEsta = props.comandas.some((atual) => atual.id === comanda.id);
    emit(jaEsta ? "detach" : "attach", jaEsta ? comanda.id : comanda);
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || `Comanda "${codigo}" não encontrada.`;
  } finally {
    carregando.value = false;
  }
}

onMounted(carregar);
</script>

<style scoped>
.seletor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 340px;
  padding: 10px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: var(--surface-card, #fff);
}

.seletor__anexadas {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--surface-border, #e5e7eb);
}

.seletor__titulo {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-color-secondary, #6b7280);
}

.seletor__fechar {
  align-self: flex-end;
}
</style>
