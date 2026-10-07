<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>Ajuste de estoque em lote</h1>
        <p>
          Some, tire ou informe o saldo contado de vários insumos de uma vez. Cada linha vira um
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
        <label class="stock-field stock-field--wide">
          <span>Adicionar insumo</span>
          <AutoComplete
            v-model="busca"
            :suggestions="sugestoes"
            option-label="name"
            placeholder="Digite o nome do insumo"
            fluid
            @complete="buscarInsumos"
            @item-select="adicionar"
          />
        </label>
      </div>
    </section>

    <section class="stock-card">
      <p v-if="!linhas.length" class="stock-empty">Nenhum insumo no ajuste. Busque acima para adicionar.</p>
      <table v-else class="bulk-adjust__table">
        <thead>
          <tr><th>Insumo</th><th>Operação</th><th>Quantidade</th><th /></tr>
        </thead>
        <tbody>
          <tr v-for="(linha, index) in linhas" :key="linha.ingredient">
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

const MODOS = [
  { label: "Entrada (+)", value: "in" },
  { label: "Saída (-)", value: "out" },
  { label: "Novo saldo", value: "set" },
];

const toast = useToast();
const locations = ref([]);
const locationId = ref(null);
const busca = ref("");
const sugestoes = ref([]);
const linhas = ref([]);
const motivo = ref("");
const salvando = ref(false);
const error = ref("");

const podeSalvar = computed(
  () => locationId.value && motivo.value.trim() && linhas.value.length
    && linhas.value.every((linha) => linha.quantity != null),
);

async function buscarInsumos({ query }) {
  const { data } = await api.get("/menu/ingredients/", { params: { search: query, is_active: true, page_size: 20 } });
  const usados = new Set(linhas.value.map((linha) => linha.ingredient));
  sugestoes.value = (data.results || data).filter((insumo) => !usados.has(String(insumo.id)));
}

function adicionar({ value }) {
  linhas.value.push({ ingredient: String(value.id), name: value.name, unit: value.unit, mode: "set", quantity: null });
  busca.value = "";
}

async function salvar() {
  salvando.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/stock/movements/bulk-adjust/", {
      location: locationId.value,
      reason: motivo.value,
      items: linhas.value.map(({ ingredient, mode, quantity }) => ({ ingredient, mode, quantity: String(quantity) })),
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

defineExpose({ linhas, motivo, locationId, salvar, adicionar });
</script>

<style scoped>
@import "../styles/stock-document.css";

.bulk-adjust__table { width: 100%; border-collapse: collapse; margin-bottom: var(--space-4); }
.bulk-adjust__table th, .bulk-adjust__table td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border); }
.bulk-adjust__table small { color: var(--text-muted); }
.bulk-adjust__actions { display: flex; justify-content: flex-end; margin-top: var(--space-4); }
</style>
