<template>
  <div class="xml-export-status">
    <div v-if="working" class="xml-export-status__line">
      <i class="pi pi-spin pi-spinner" />
      <div>
        <strong>{{ job.status === "queued" ? "Na fila" : "Montando o ZIP" }} — {{ job.total }} nota(s)</strong>
        <p>Pode sair desta página: o aviso chega no sino quando o ZIP ficar pronto.</p>
      </div>
    </div>

    <Message v-else-if="job.status === 'failed'" severity="error" :closable="false">
      A exportação parou por um erro inesperado. Gere de novo; se repetir, avise o suporte.
    </Message>

    <Message v-else-if="!result.total" severity="info" :closable="false">
      Nenhum XML entrou no ZIP{{ result.quantidade_de_falhas ? ": todas as notas do filtro falharam (veja abaixo)." : "." }}
    </Message>

    <Message v-else-if="job.expired" severity="warn" :closable="false">
      O ZIP passou das 24 horas e foi apagado. Gere a exportação de novo.
    </Message>

    <div v-else class="xml-export-status__line xml-export-status__line--ready">
      <i class="pi pi-check-circle" />
      <div>
        <strong>{{ result.total }} XML(s) em {{ result.nome }}</strong>
        <p>Disponível para baixar até {{ dateTime(job.expires_at) }}. Depois o arquivo é apagado.</p>
      </div>
      <Button label="Baixar ZIP" icon="pi pi-download" :loading="downloading" @click="emit('download')" />
    </div>

    <div v-if="result.quantidade_de_falhas" class="xml-export-status__failures">
      <strong>{{ result.quantidade_de_falhas }} nota(s) ficaram de fora</strong>
      <ul>
        <li v-for="falha in result.falhas" :key="`${falha.numero}-${falha.chave}`">
          Nota {{ falha.numero }}: {{ falha.motivo }}
        </li>
      </ul>
      <small v-if="result.quantidade_de_falhas > result.falhas.length">A lista completa está em falhas.txt, dentro do ZIP.</small>
    </div>

    <div v-if="!working" class="xml-export-status__actions">
      <Button label="Nova exportação" icon="pi pi-plus" severity="secondary" outlined @click="emit('again')" />
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import Button from "primevue/button";
import Message from "primevue/message";

const props = defineProps({
  job: { type: Object, required: true },
  downloading: { type: Boolean, default: false },
});
const emit = defineEmits(["download", "again"]);

const working = computed(() => ["queued", "running"].includes(props.job.status));
const result = computed(() => ({ falhas: [], ...(props.job.result || {}) }));
const dateTime = (value) => (value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");
</script>

<style scoped>
.xml-export-status { display: flex; flex-direction: column; gap: 14px; }
.xml-export-status__line { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.xml-export-status__line > div { flex: 1; min-width: 200px; }
.xml-export-status__line > .pi { font-size: 22px; color: var(--text-brand); }
.xml-export-status__line--ready > .pi { color: var(--success-text); }
.xml-export-status__line strong { color: var(--text-strong); }
.xml-export-status__line p { margin: 4px 0 0; color: var(--text-muted); }
.xml-export-status__failures { padding: 12px 14px; border: 1px solid var(--border); border-left: 3px solid var(--warning); border-radius: var(--radius-md); }
.xml-export-status__failures ul { margin: 8px 0; padding-left: 18px; color: var(--text-body); }
.xml-export-status__failures small { color: var(--text-muted); }
.xml-export-status__actions { display: flex; justify-content: flex-end; }
</style>
