<template>
  <main class="cmd-history">
    <header class="cmd-history__header">
      <div>
        <button class="cmd-history__back" type="button" @click="router.back()">← Voltar</button>
        <small>HISTÓRICO DA COMANDA</small>
        <h1>{{ titulo }}</h1>
        <p>Lançamentos, produção, cancelamentos, zeramentos e cobranças — do mais novo para o mais antigo.</p>
      </div>
      <form class="cmd-history__filters" @submit.prevent="buscar">
        <label>De <input v-model="depois" class="cmd-history__date" type="date" /></label>
        <label>Até <input v-model="antes" class="cmd-history__date" type="date" /></label>
        <Button type="submit" label="Filtrar" icon="pi pi-filter" severity="secondary" outlined />
      </form>
    </header>

    <div v-if="carregando" class="cmd-history__state">Carregando histórico…</div>
    <div v-else-if="erro" class="cmd-history__state cmd-history__state--error" role="alert">{{ erro }}</div>
    <div v-else-if="!linhas.length" class="cmd-history__state">Nada aconteceu com esta comanda no período.</div>
    <Card v-else :title="`${total} ${total === 1 ? 'evento' : 'eventos'}`" padding="none">
      <ReportDataTable :rows="linhas" :columns="colunasDoHistorico" />
    </Card>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";

import ReportDataTable from "../components/data/ReportDataTable.vue";
import Card from "../components/display/Card.vue";
import { api } from "../services/api";
import { colunasDoHistorico, linhaDoHistorico } from "../services/commandHistory";
import { normalizeApiError } from "../utils/apiError";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();

const comanda = ref(null);
const linhas = ref([]);
const total = ref(0);
const depois = ref("");
const antes = ref("");
const carregando = ref(false);
const erro = ref("");

const titulo = computed(() => (comanda.value ? `Comanda ${comanda.value.number}` : "Comanda"));

async function buscar() {
  carregando.value = true;
  erro.value = "";
  try {
    const filtros = { all: "1" };
    if (depois.value) filtros.after = depois.value;
    if (antes.value) filtros.before = antes.value;
    const { data } = await api.get(`/commands/${props.id}/history/`, { params: filtros });
    const eventos = data.results || [];
    comanda.value = data.command || comanda.value;
    linhas.value = eventos.map(linhaDoHistorico);
    total.value = data.count || eventos.length;
  } catch (exc) {
    erro.value = normalizeApiError(exc).message || "Não foi possível carregar o histórico.";
  } finally {
    carregando.value = false;
  }
}

onMounted(buscar);
</script>

<style scoped>
.cmd-history{display:flex;flex-direction:column;gap:var(--page-section-gap);max-width:1280px;margin:0 auto}
.cmd-history__header{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;flex-wrap:wrap}
.cmd-history__header>div{display:flex;flex-direction:column;gap:5px}
.cmd-history__header h1,.cmd-history__header p{margin:0}
.cmd-history__header p{color:var(--text-muted)}
.cmd-history__header small{color:var(--brand);font-weight:700;letter-spacing:.08em}
.cmd-history__back{align-self:flex-start;border:0;background:none;color:var(--text-muted);cursor:pointer;padding:0 0 8px}
.cmd-history__filters{display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap}
.cmd-history__filters label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text-muted)}
.cmd-history__date{height:38px;padding:0 10px;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-card);color:var(--text)}
.cmd-history__state{padding:40px;text-align:center;color:var(--text-muted)}
.cmd-history__state--error{color:var(--danger-text)}
@media(max-width:720px){.cmd-history__header{flex-direction:column;align-items:stretch}}
</style>
