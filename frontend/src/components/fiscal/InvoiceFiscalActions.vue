<template>
  <span class="invoice-fiscal-actions">
    <Button v-if="canResend" label="Reenviar nota" severity="secondary" outlined icon="pi pi-send" :loading="busy === 'resend'" :disabled="!!busy" @click="resend" />
    <Button v-if="canRecreate" label="Recriar nota" severity="secondary" outlined icon="pi pi-refresh" :loading="busy === 'recreate'" :disabled="!!busy" @click="confirmRecreate" />
    <Button v-if="canDownloadXml" label="Baixar XML" severity="secondary" outlined icon="pi pi-download" :loading="busy === 'xml'" :disabled="!!busy" @click="downloadXml" />
  </span>
</template>

<script setup>
import { computed, ref } from "vue";
import Button from "primevue/button";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { baixarArquivo } from "../../utils/baixarArquivo";
import { fiscalStateOf, RECREATABLE_STATES, RESENDABLE_STATES, STATES_WITH_XML } from "./invoiceFiscalState";

// `invoice` é a nota inteira (tela da nota) ou o resumo `fiscal` do pedido
// (tela do pedido). Os dois trazem `id` e `status`; o resumo já traz
// `fiscal_state`, e da nota inteira ele é derivado como o backend faz.
const props = defineProps({ invoice: { type: Object, required: true } });
const emit = defineEmits(["changed"]);
const confirm = useConfirm();
const toast = useToast();
const busy = ref("");

const state = computed(() => fiscalStateOf(props.invoice));
const canResend = computed(() => RESENDABLE_STATES.includes(state.value));
const canRecreate = computed(() => RECREATABLE_STATES.includes(state.value));
const canDownloadXml = computed(() => ("xml_content" in props.invoice
  ? Boolean(props.invoice.xml_content)
  : STATES_WITH_XML.includes(state.value)));

async function run(kind, request, onSuccess, errorSummary) {
  busy.value = kind;
  try {
    onSuccess(await request());
  } catch (error) {
    // O download já devolve o erro normalizado; o POST devolve o do axios.
    const detail = error?.isAxiosError ? normalizeApiError(error).message : error?.message;
    toast.add({ severity: "error", summary: errorSummary, detail, life: 7000 });
  } finally {
    busy.value = "";
    if (kind !== "xml") emit("changed");
  }
}

function resend() {
  run("resend", async () => (await api.post(`/invoices/${props.invoice.id}/resend/`, {}, { timeout: 60_000 })).data, (data) => {
    const issued = data.status === "issued";
    toast.add({ severity: issued ? "success" : "info", summary: issued ? "Nota autorizada" : "Nota reenviada", detail: issued ? "A SEFAZ autorizou a nota." : "A nota continua em processamento.", life: 4500 });
  }, "Não foi possível reenviar a nota");
}

function confirmRecreate() {
  confirm.require({
    header: "Recriar nota",
    icon: "pi pi-refresh",
    message: "A tentativa travada (XML, chave e contingência) é descartada e a nota é emitida de novo, com a data de hoje e o mesmo número. Use quando o reenvio não resolve — por exemplo, depois das 24 h da contingência. Um cupom de contingência já impresso deixa de valer.",
    acceptLabel: "Recriar",
    rejectLabel: "Cancelar",
    accept: recreate,
  });
}

function recreate() {
  run("recreate", async () => (await api.post(`/invoices/${props.invoice.id}/recreate/`, {}, { timeout: 60_000 })).data, (data) => {
    const issued = data.status === "issued";
    toast.add({
      severity: issued ? "success" : data.status === "error" ? "warn" : "info",
      summary: issued ? "Nota recriada e autorizada" : "Nota recriada",
      detail: issued ? "A SEFAZ autorizou a nova emissão." : data.error_message || "A nova emissão está em andamento.",
      life: 6000,
    });
  }, "Não foi possível recriar a nota");
}

function downloadXml() {
  const name = props.invoice.access_key ? `${props.invoice.access_key}.xml` : `nota-${props.invoice.number || props.invoice.id}.xml`;
  run("xml", () => baixarArquivo(`/invoices/${props.invoice.id}/xml/`, name), () => {}, "Não foi possível baixar o XML");
}
</script>

<style scoped>
/* Os botoes entram direto no flex do cabecalho da pagina. */
.invoice-fiscal-actions { display: contents; }
</style>
