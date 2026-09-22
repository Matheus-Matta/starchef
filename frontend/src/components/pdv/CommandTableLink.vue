<template>
  <div class="mesa">
    <button
      class="mesa__botao"
      type="button"
      :disabled="ocupado"
      @click="abrir = !abrir"
    >
      <span class="mesa__rotulo">
        <template v-if="numeroAtual">Mesa <strong>{{ numeroAtual }}</strong></template>
        <template v-else>Sem mesa</template>
      </span>
      <span class="mesa__acao">{{ numeroAtual ? "Trocar" : "Vincular a uma mesa" }}</span>
    </button>

    <div v-if="abrir" class="mesa__seletor">
      <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>

      <button
        v-if="numeroAtual"
        class="pdv-btn pdv-btn--ghost mesa__soltar"
        type="button"
        :disabled="ocupado"
        @click="desvincular"
      >
        Tirar da mesa {{ numeroAtual }}
      </button>

      <div class="pdv-scroll mesa__lista">
        <p v-if="carregando && !mesas.length" class="pdv-empty">Carregando…</p>
        <p v-else-if="!mesas.length" class="pdv-empty">Nenhuma mesa ativa.</p>
        <button
          v-for="opcao in mesas"
          :key="opcao.id"
          type="button"
          class="pdv-card mesa__opcao"
          :class="{ 'pdv-card--active': String(opcao.id) === String(comanda.current_table) }"
          :disabled="ocupado"
          @click="vincular(opcao)"
        >
          <strong>{{ opcao.number }}</strong>
          <small class="pdv-muted">{{ opcao.sector_name || "" }}</small>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * Onde este cartão está sentado — e o gesto de mudar isso.
 *
 * Faltava na tela de comandas, e era o lugar natural: quem está olhando um
 * cartão é quem sabe para qual mesa ele foi. Antes, vincular só existia no
 * meio do fluxo de abrir pedido, então um cartão que sentou na mesa errada
 * só era corrigido na hora de cobrar.
 *
 * O vínculo é da COMANDA, não do pedido: é ela que anda pelo salão e decide a
 * ocupação. O pedido guarda a mesa só como histórico.
 */
import { computed, ref, watch } from "vue";

import {
  fetchTables,
  linkCommandToTable,
  unlinkCommandFromTable,
} from "../../services/commandService";

const props = defineProps({
  comanda: { type: Object, required: true },
  restaurantId: { type: [String, Number], default: null },
});

const emit = defineEmits(["changed"]);

const abrir = ref(false);
const mesas = ref([]);
const carregando = ref(false);
const ocupado = ref(false);
const erro = ref("");

const numeroAtual = computed(() => props.comanda?.current_table_number || null);

async function carregar() {
  carregando.value = true;
  erro.value = "";
  try {
    mesas.value = await fetchTables(props.restaurantId);
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || "Não foi possível listar as mesas.";
  } finally {
    carregando.value = false;
  }
}

async function vincular(mesa) {
  await _executar(() => linkCommandToTable(props.comanda.id, mesa.id));
}

async function desvincular() {
  await _executar(() => unlinkCommandFromTable(props.comanda.id));
}

async function _executar(acao) {
  ocupado.value = true;
  erro.value = "";
  try {
    await acao();
    abrir.value = false;
    // Quem recarrega é o pai: a comanda que ele tem em mãos mudou, e
    // devolver só o número aqui deixaria as duas cópias divergindo.
    emit("changed");
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || "Não foi possível mudar a mesa.";
  } finally {
    ocupado.value = false;
  }
}

watch(abrir, (aberto) => {
  if (aberto) carregar();
});

// Trocar de cartão fecha o seletor: ele era do cartão anterior.
watch(() => props.comanda?.id, () => (abrir.value = false));
</script>

<style scoped>
.mesa {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mesa__botao {
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

.mesa__rotulo {
  font-size: 13px;
}

.mesa__acao {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color, #2563eb);
}

.mesa__seletor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  padding: 10px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: var(--surface-card, #fff);
}

.mesa__lista {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
  gap: 6px;
}

.mesa__opcao {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.mesa__soltar {
  align-self: flex-start;
}
</style>
