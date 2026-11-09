<template>
  <div class="consumption-activity">
    <section class="stock-card">
      <div class="stock-card__head">
        <div>
          <h2>Vai faltar?</h2>
          <p>{{ forecast.data ? `Próxima baixa em ${formatDate(forecast.data)}` : "Sem próxima baixa" }} — comparado com o saldo de agora.</p>
        </div>
        <Button v-if="forecast.baixa_aqui" label="Executar agora" icon="pi pi-play" outlined size="small" :loading="running" @click="confirmRun" />
      </div>
      <div v-if="forecast.baixa_aqui === false" class="stock-doc__alert stock-doc__alert--info">
        <i class="pi pi-cloud" /> <span>A baixa é feita pela nuvem. Esta loja recebe a saída e o histórico pela sincronização.</span>
      </div>
      <div v-for="aviso in forecast.avisos" :key="aviso" class="stock-doc__alert stock-doc__alert--warn">
        <i class="pi pi-exclamation-circle" /> <span>{{ aviso }}</span>
      </div>
      <DataTable :value="forecast.linhas" size="small" class="stock-table" :loading="loading">
        <Column field="nome" header="Insumo" />
        <Column header="Precisa"><template #body="{ data }">{{ qty(data.precisa, data.unidade) }}</template></Column>
        <Column header="Saldo no local"><template #body="{ data }">{{ qty(data.saldo, data.unidade) }}</template></Column>
        <Column header="Falta">
          <template #body="{ data }">
            <Tag v-if="Number(data.falta) > 0" :value="qty(data.falta, data.unidade)" severity="danger" rounded />
            <span v-else>—</span>
          </template>
        </Column>
      </DataTable>
    </section>

    <section class="stock-card">
      <h2>Execuções</h2>
      <p v-if="!history.length" class="consumption-muted">Nenhuma baixa feita ainda.</p>
      <div v-for="item in history" :key="item.id" class="consumption-run">
        <strong>{{ formatDate(item.data) }}</strong>
        <Tag :value="item.situacao_label" :severity="SEVERITY[item.situacao]" rounded />
        <span class="consumption-muted">{{ runDetail(item) }}</span>
        <Button v-if="item.saida" label="Ver saída" icon="pi pi-external-link" text size="small" @click="openExit(item.saida)" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Tag from "primevue/tag";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({ menuId: { type: String, required: true } });
const router = useRouter();
const confirm = useConfirm();
const toast = useToast();
const forecast = ref({ data: null, linhas: [], avisos: [] });
const history = ref([]);
const loading = ref(false);
const running = ref(false);
const SEVERITY = { posted: "success", draft: "info", no_stock: "warning", failed: "danger" };

const formatDate = (value) => (value ? new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR") : "");
const qty = (value, unit) => `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 3 })} ${unit}`;

function openExit(id) {
  router.push({ name: "estoque-saida-documento", params: { id } });
}

function runDetail(item) {
  const faltas = (item.faltas || []).map((f) => `faltou ${qty(f.faltou, f.unidade)} de ${f.nome}`).join("; ");
  return [faltas, item.mensagem].filter(Boolean).join(" · ");
}

async function load() {
  loading.value = true;
  try {
    const base = `/stock/consumption-menus/${props.menuId}`;
    const [previsao, historico] = await Promise.all([api.get(`${base}/previsao/`), api.get(`${base}/historico/`)]);
    forecast.value = previsao.data;
    history.value = historico.data;
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar a previsão", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    loading.value = false;
  }
}

function confirmRun() {
  confirm.require({
    header: "Executar agora",
    icon: "pi pi-play",
    message: "Faz a baixa de HOJE agora, sem esperar o horário. Cada cardápio baixa uma vez por dia: depois disso o agendador não baixa de novo hoje.",
    acceptLabel: "Executar",
    rejectLabel: "Cancelar",
    accept: run,
  });
}

async function run() {
  running.value = true;
  try {
    const { data } = await api.post(`/stock/consumption-menus/${props.menuId}/executar/`, {}, { timeout: 60_000 });
    toast.add({ severity: SEVERITY[data.situacao] === "danger" ? "error" : "success", summary: data.situacao_label, detail: runDetail(data), life: 6000 });
  } catch (error) {
    toast.add({ severity: "warn", summary: "Não executado", detail: normalizeApiError(error).message, life: 6000 });
  } finally {
    running.value = false;
    await load();
  }
}

onMounted(load);
defineExpose({ load });
</script>

<style scoped>
/* `scoped` não atravessa componentes: sem isto os cartões saíam sem estilo. */
@import "../../styles/stock-document.css";

/* As duas seções entram direto na coluna da página. */
.consumption-activity { display: contents; }
.consumption-run { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid var(--border-subtle); }
.consumption-muted { color: var(--text-muted); }
/* O alerta base é vermelho (erro); previsão e "baixa na nuvem" não são erro. */
.stock-doc__alert--warn { border-color: transparent; background: var(--warning-subtle); color: var(--warning-text); }
.stock-doc__alert--info { border-color: transparent; background: var(--info-subtle); color: var(--info-text); }
</style>
