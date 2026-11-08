<template>
  <main class="xml-export">
    <header class="xml-export__header">
      <button class="xml-export__back" type="button" @click="router.push({ name: 'notas-fiscais' })">← Notas fiscais</button>
      <small>FISCAL</small>
      <h1>Exportar XML das notas</h1>
      <p>Um ZIP com o XML de cada nota do período, separado por situação. Pouca coisa sai na hora; o resto é montado em segundo plano e o aviso chega no sino.</p>
    </header>

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

    <Card v-if="id" title="Exportação" :subtitle="job ? `Pedida em ${dateTime(job.created_at)}` : ''">
      <div v-if="!job" class="xml-export__state"><i class="pi pi-spin pi-spinner" /> Carregando…</div>
      <XmlExportStatus v-else :job="job" :downloading="downloading" @download="download" @again="newExport" />
    </Card>

    <Card v-else title="Filtros" subtitle="O período é pela data de emissão da nota.">
      <XmlExportForm :loading="sending" @submit="generate" />
    </Card>
  </main>
</template>

<script setup>
import { onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import Message from "primevue/message";
import { useToast } from "primevue/usetoast";

import Card from "../components/display/Card.vue";
import XmlExportForm from "../components/fiscal/XmlExportForm.vue";
import XmlExportStatus from "../components/fiscal/XmlExportStatus.vue";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";
import { baixarArquivo } from "../utils/baixarArquivo";

const props = defineProps({ id: { type: String, default: "" } });
const router = useRouter();
const toast = useToast();
const job = ref(null);
const error = ref("");
const sending = ref(false);
const downloading = ref(false);
let timer = null;

const dateTime = (value) => (value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

async function load() {
  clearTimeout(timer);
  if (!props.id) {
    job.value = null;
    return;
  }
  try {
    job.value = (await api.get(`/invoices/xml-export/${props.id}/`, { skipRestaurantScope: true })).data;
    error.value = "";
    // Enquanto o worker monta, a página acompanha sozinha; o sino avisa também.
    if (["queued", "running"].includes(job.value.status)) timer = setTimeout(load, 4000);
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  }
}

async function generate(filters) {
  sending.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/invoices/xml-export/", filters, { skipRestaurantScope: true, timeout: 120_000 });
    if (!data.id) {
      toast.add({ severity: "info", summary: "Nada para exportar", detail: data.detail, life: 5000 });
      return;
    }
    await router.replace({ name: "notas-fiscais-exportar-xml", params: { id: data.id } });
    if (data.download_url) await download(data);
    else toast.add({ severity: "info", summary: "Exportação na fila", detail: data.message, life: 6000 });
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  } finally {
    sending.value = false;
  }
}

async function download(target = job.value) {
  if (!target?.download_url) return;
  downloading.value = true;
  try {
    await baixarArquivo(target.download_url, target.result?.nome || "notas-fiscais.zip");
  } catch (cause) {
    toast.add({ severity: "error", summary: "Não foi possível baixar o ZIP", detail: cause.message, life: 7000 });
    await load();
  } finally {
    downloading.value = false;
  }
}

function newExport() {
  router.push({ name: "notas-fiscais-exportar-xml" });
}

watch(() => props.id, load, { immediate: true });
onUnmounted(() => clearTimeout(timer));
</script>

<style scoped>
.xml-export { display: flex; flex-direction: column; gap: var(--page-section-gap); max-width: 860px; margin: 0 auto; width: 100%; }
.xml-export__header { display: flex; flex-direction: column; gap: 6px; }
.xml-export__header h1, .xml-export__header p { margin: 0; }
.xml-export__header h1 { color: var(--text-strong); font: var(--weight-extra) 24px/1.15 var(--font-sans); }
.xml-export__header small { color: var(--text-brand); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: var(--tracking-caps); }
.xml-export__header p, .xml-export__state { color: var(--text-muted); }
.xml-export__back { align-self: flex-start; border: 0; background: none; color: var(--text-brand); cursor: pointer; padding: 0; }
</style>
