<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>Ajuste de estoque em lote</h1>
        <p>
          Some, tire ou informe o saldo contado de produtos e insumos. Cada linha vira um
          movimento de ajuste com o motivo e quem fez.
        </p>
      </div>
    </header>

    <div v-if="error" class="stock-doc__alert"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <section class="stock-card">
      <div class="stock-grid">
        <label class="stock-field">
          <span>Local</span>
          <Select
            v-model="locationId"
            :options="locations"
            option-label="name"
            option-value="id"
            placeholder="Escolha o local"
            fluid
          />
        </label>
        <label class="stock-field">
          <span>Tipo de item</span>
          <Select
            v-model="tipoSelecionado"
            :options="TIPOS_DE_ITEM"
            option-label="label"
            option-value="value"
            fluid
            @change="busca = ''; sugestoes = []"
          />
        </label>
        <label class="stock-field stock-field--wide">
          <span>Adicionar {{ tipoAtual.label.toLowerCase() }}</span>
          <AutoComplete
            v-model="busca"
            :suggestions="sugestoes"
            option-label="name"
            placeholder="Digite o nome ou código"
            fluid
            @complete="buscarItens"
            @item-select="adicionar"
          />
        </label>
      </div>
    </section>

    <section class="stock-card">
      <p v-if="!linhas.length" class="stock-empty">Nenhum item no ajuste. Busque acima para adicionar.</p>
      <table v-else class="bulk-adjust__table">
        <thead>
          <tr><th>Item</th><th>Operação</th><th>Quantidade</th><th /></tr>
        </thead>
        <tbody>
          <tr v-for="(linha, index) in linhas" :key="`${linha.kind}:${linha.id}`">
            <td>{{ linha.name }} <small>{{ linha.unit }}</small></td>
            <td>
              <Select v-model="linha.mode" :options="MODOS" option-label="label" option-value="value" />
            </td>
            <td><InputNumber v-model="linha.quantity" :min="0" :max-fraction-digits="3" /></td>
            <td>
              <Button icon="pi pi-trash" text rounded aria-label="Remover" @click="linhas.splice(index, 1)" />
            </td>
          </tr>
        </tbody>
      </table>
      <label class="stock-field stock-field--wide">
        <span>Motivo (obrigatório)</span>
        <Textarea v-model="motivo" rows="2" placeholder="Ex.: inventário de fim de mês" fluid />
      </label>
      <div class="bulk-adjust__actions">
        <Button label="Aplicar ajuste" icon="pi pi-check" :loading="salvando" :disabled="!podeSalvar" @click="salvar" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import AutoComplete from "primevue/autocomplete";
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import Select from "primevue/dropdown";
import Textarea from "primevue/textarea";
import { useToast } from "primevue/usetoast";

import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";
import { STOCK_ITEM_TYPES, stockItemType } from "../utils/stockBulkAdjustTypes";

const MODOS = [
  { label: "Entrada (+)", value: "in" },
  { label: "Saída (-)", value: "out" },
  { label: "Novo saldo", value: "set" },
];
const TIPOS_DE_ITEM = STOCK_ITEM_TYPES;

const toast = useToast();
const locations = ref([]);
const locationId = ref(null);
const busca = ref("");
const sugestoes = ref([]);
const linhas = ref([]);
const tipoSelecionado = ref("ingredient");
const motivo = ref("");
const salvando = ref(false);
const error = ref("");
const tipoAtual = computed(() => stockItemType(tipoSelecionado.value));

const podeSalvar = computed(
  () => locationId.value && motivo.value.trim() && linhas.value.length
    && linhas.value.every((linha) => linha.quantity != null),
);

async function buscarItens({ query }) {
  const tipo = tipoAtual.value;
  const params = { search: query, is_active: true, ...(tipo.itemType ? { item_type: tipo.itemType } : {}), page_size: 20 };
  const { data } = await api.get(tipo.endpoint, { params });
  const usados = new Set(linhas.value.map((linha) => `${linha.kind}:${linha.id}`));
  sugestoes.value = (data.results || data).filter((item) => !usados.has(`${tipo.kind}:${item.id}`));
}

function adicionar({ value }, kind = tipoAtual.value.kind) {
  linhas.value.push({ id: String(value.id), kind, name: value.name, unit: value.unit || value.stock_unit, mode: "set", quantity: null });
  busca.value = "";
}

async function salvar() {
  salvando.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/stock/movements/bulk-adjust/", {
      location: locationId.value,
      reason: motivo.value,
      items: linhas.value.map(({ id, kind, mode, quantity }) => ({ [kind]: id, mode, quantity: String(quantity) })),
    });
    toast.add({ severity: "success", summary: "Ajuste aplicado", detail: `${data.created} movimento(s) registrado(s).`, life: 4000 });
    linhas.value = [];
    motivo.value = "";
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    salvando.value = false;
  }
}

onMounted(async () => {
  const { data } = await api.get("/stock/locations/", { params: { is_active: true, page_size: 100 } });
  locations.value = data.results || data;
  if (locations.value.length === 1) locationId.value = locations.value[0].id;
});

defineExpose({ linhas, motivo, locationId, tipoSelecionado, salvar, adicionar, buscarItens });
</script>

<style scoped>
@import "../styles/stock-document.css";

.bulk-adjust__table { width: 100%; border-collapse: collapse; margin-bottom: var(--space-4); }
.bulk-adjust__table th, .bulk-adjust__table td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border); }
.bulk-adjust__table small { color: var(--text-muted); }
.bulk-adjust__actions { display: flex; justify-content: flex-end; margin-top: var(--space-4); }
</style>
