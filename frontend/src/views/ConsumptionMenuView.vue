<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>{{ id ? form.nome || "Cardápio de consumo" : "Novo cardápio de consumo" }}</h1>
        <p>O que sai do estoque sozinho, no dia certo. Cada execução vira uma saída de estoque comum.</p>
      </div>
      <div class="stock-doc__head-actions">
        <Button label="Voltar" icon="pi pi-arrow-left" text @click="voltarParaLista(router, 'cardapios-consumo')" />
        <Button label="Salvar" icon="pi pi-save" :loading="saving" :disabled="loading" @click="save" />
      </div>
    </header>

    <div v-if="error" class="stock-doc__alert"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>
    <div v-if="loading" class="stock-card"><Skeleton height="220px" /></div>

    <template v-else>
      <section class="stock-card">
        <h2>Quando e de onde sai</h2>
        <div class="stock-grid">
          <label class="stock-field stock-field--wide">
            <span>Nome *</span>
            <InputText v-model="form.nome" placeholder="Ex.: Buffet de terça" fluid />
          </label>
          <label class="stock-field stock-field--wide">
            <span>Local de estoque *</span>
            <Select v-model="form.local" :options="locations" option-label="name" option-value="id" placeholder="Selecione" fluid />
          </label>
          <label class="stock-field">
            <span>Repete *</span>
            <Select v-model="form.frequencia" :options="FREQUENCIAS" option-label="label" option-value="value" fluid />
          </label>
          <div v-if="form.frequencia === 'weekly'" class="stock-field stock-field--wide">
            <span>Dias da semana *</span>
            <SelectButton v-model="form.dias_da_semana" :options="DIAS" option-label="label" option-value="value" multiple />
          </div>
          <label v-if="form.frequencia === 'monthly'" class="stock-field">
            <span>Dia do mês *</span>
            <InputNumber v-model="form.dia_do_mes" :min="1" :max="31" fluid />
            <small>Se o mês não tiver esse dia, vale o último (31 → 28 em fevereiro).</small>
          </label>
          <label class="stock-field">
            <span>Horário da baixa</span>
            <InputText v-model="form.horario" type="time" fluid />
          </label>
          <label class="stock-field">
            <span>Começa em</span>
            <InputText v-model="form.comeca_em" type="date" fluid />
          </label>
          <div class="stock-field stock-field--wide">
            <span>Confirmação</span>
            <div class="consumption-switch">
              <InputSwitch v-model="form.confirma_sozinho" />
              <div>
                <strong>{{ form.confirma_sozinho ? "Confirma sozinho" : "Fica para conferir" }}</strong>
                <small>{{ form.confirma_sozinho ? "O estoque baixa no horário, sem ninguém." : "A saída nasce em rascunho e alguém confirma o peso." }}</small>
              </div>
            </div>
          </div>
          <div class="stock-field">
            <span>Situação</span>
            <div class="consumption-switch">
              <InputSwitch v-model="form.ativo" />
              <div><strong>{{ form.ativo ? "Ativo" : "Pausado" }}</strong></div>
            </div>
          </div>
          <label class="stock-field stock-field--full">
            <span>Observações</span>
            <Textarea v-model="form.observacoes" rows="2" fluid />
          </label>
        </div>
      </section>

      <ConsumptionMenuItems v-model="rows" />
      <ConsumptionMenuActivity v-if="id" :key="activityKey" :menu-id="id" />
    </template>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { voltarParaLista } from "../utils/voltarParaLista";
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Select from "primevue/dropdown";
import SelectButton from "primevue/selectbutton";
import Skeleton from "primevue/skeleton";
import Textarea from "primevue/textarea";
import { useToast } from "primevue/usetoast";

import ConsumptionMenuActivity from "../components/stock/ConsumptionMenuActivity.vue";
import ConsumptionMenuItems from "../components/stock/ConsumptionMenuItems.vue";
import { CONSUMPTION_FREQUENCY_LABELS } from "../config/consumptionMenuResource";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const props = defineProps({ id: { type: String, default: "" } });
const router = useRouter();
const toast = useToast();
const FREQUENCIAS = Object.entries(CONSUMPTION_FREQUENCY_LABELS).map(([value, label]) => ({ value, label }));
const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((label, value) => ({ value, label }));

const form = reactive({
  nome: "", local: null, frequencia: "daily", dias_da_semana: [], dia_do_mes: null, horario: "06:00",
  comeca_em: new Date().toLocaleDateString("sv-SE"), confirma_sozinho: false, ativo: true, observacoes: "",
});
const rows = ref([]);
const locations = ref([]);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const activityKey = ref(0);

function fromItem(item) {
  const tipo = item.ingredient ? "ingredient" : "product";
  return { _key: `${tipo}:${item.ingredient || item.product}`, tipo, nome: item.nome, unidadeBase: item.unidade_do_insumo || "",
           ingredient: item.ingredient, product: item.product, quantidade: Number(item.quantidade), unidade: item.unidade || "" };
}

function payload() {
  return {
    ...form,
    horario: (form.horario || "06:00").slice(0, 5),
    itens: rows.value.map((row) => ({
      ingredient: row.tipo === "ingredient" ? row.ingredient : null,
      product: row.tipo === "product" ? row.product : null,
      quantidade: row.quantidade,
      unidade: row.tipo === "ingredient" ? row.unidade : "",
    })),
  };
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const { data } = props.id
      ? await api.put(`/stock/consumption-menus/${props.id}/`, payload())
      : await api.post("/stock/consumption-menus/", payload());
    toast.add({ severity: "success", summary: "Cardápio salvo", detail: `${data.quando}. Próxima: ${data.proximas_datas[0] || "—"}`, life: 5000 });
    if (!props.id) await router.replace({ name: "cardapio-consumo-documento", params: { id: data.id } });
    activityKey.value += 1;
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    const [locais, atual] = await Promise.all([
      api.get("/stock/locations/", { params: { is_active: true, page_size: 200 } }),
      props.id ? api.get(`/stock/consumption-menus/${props.id}/`) : Promise.resolve(null),
    ]);
    locations.value = locais.data.results || locais.data;
    if (atual) {
      Object.assign(form, { ...atual.data, horario: String(atual.data.horario || "").slice(0, 5) });
      rows.value = atual.data.itens.map(fromItem);
    } else if (locations.value.length === 1) {
      form.local = locations.value[0].id;
    }
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
@import "../styles/stock-document.css";

.consumption-switch { display: flex; align-items: center; gap: 12px; min-height: var(--control-h); }
.consumption-switch > div { display: flex; flex-direction: column; gap: 2px; }
.consumption-switch strong { color: var(--text-strong); font-size: 13px; }
</style>
