<template>
  <div class="cosmos-page">
    <header class="cosmos-head">
      <div>
        <span class="cosmos-eyebrow">INTEGRAÇÃO FISCAL</span>
        <h1>Bluesoft Cosmos</h1>
        <p>Configure a credencial desta conta para sugerir NCM e CEST ao criar perfis fiscais.</p>
      </div>
      <Tag :value="statusLabel" :severity="statusSeverity" rounded />
    </header>

    <div v-if="loading" class="cosmos-card cosmos-card--loading">
      <Skeleton width="180px" height="22px" />
      <Skeleton width="100%" height="44px" />
      <Skeleton width="100%" height="44px" />
    </div>

    <form v-else class="cosmos-card" novalidate @submit.prevent="save">
      <section class="cosmos-section">
        <div class="cosmos-section__head">
          <div>
            <h2>Conta da API</h2>
            <p>O token pertence somente a esta conta StarChef e nunca é devolvido pela API.</p>
          </div>
          <div class="cosmos-toggle">
            <InputSwitch v-model="form.is_active" input-id="cosmos-active" />
            <label for="cosmos-active">{{ form.is_active ? "Integração ativa" : "Integração desativada" }}</label>
          </div>
        </div>

        <div class="cosmos-grid">
          <label class="cosmos-field cosmos-field--full">
            <span>Token da API Cosmos</span>
            <SecretField
              v-model="form.api_token"
              :configured="form.api_token_configured"
              :revealing="revealingToken"
              placeholder="Cole o X-Cosmos-Token"
              @edit="startEditingToken"
            />
          </label>

          <label class="cosmos-field cosmos-field--full">
            <span>User-Agent fornecido pela Cosmos</span>
            <InputText v-model.trim="form.user_agent" placeholder="Exatamente como aparece junto ao token" fluid />
            <small>A Cosmos exige o token e este User-Agent em todas as consultas.</small>
          </label>

          <label class="cosmos-field">
            <span>Timeout (segundos)</span>
            <InputNumber v-model="form.timeout_seconds" :min="1" :max="60" :use-grouping="false" fluid />
          </label>
        </div>
      </section>

      <Message severity="info" :closable="false">
        A busca usa o nome do perfil e preenche apenas os campos encontrados. A classificação é uma sugestão e deve ser revisada antes da emissão fiscal.
      </Message>

      <Message v-if="errorMessage" severity="error" :closable="false">{{ errorMessage }}</Message>

      <footer class="cosmos-actions">
        <a href="https://api.cosmos.bluesoft.com.br/api" target="_blank" rel="noopener noreferrer">Abrir documentação da Cosmos</a>
        <Button type="submit" label="Salvar configuração" icon="pi pi-check" :loading="saving" />
      </footer>
    </form>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Message from "primevue/message";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";

import SecretField from "../components/form/SecretField.vue";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const toast = useToast();
const loading = ref(true);
const saving = ref(false);
const errorMessage = ref("");
const revealingToken = ref(false);
const form = reactive({
  api_token: "",
  api_token_configured: false,
  user_agent: "",
  timeout_seconds: 10,
  is_active: false,
  is_ready: false,
});

const statusLabel = computed(() => form.is_ready ? "Ativa e pronta" : form.is_active ? "Configuração incompleta" : "Desativada");
const statusSeverity = computed(() => form.is_ready ? "success" : form.is_active ? "warning" : "secondary");

function applyConfig(data) {
  Object.assign(form, data, { api_token: "" });
  revealingToken.value = false;
}

function startEditingToken() {
  revealingToken.value = true;
  form.api_token = "";
}

async function load() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const { data } = await api.get("/integrations/cosmos/config/", { skipRestaurantScope: true });
    applyConfig(data);
  } catch (error) {
    errorMessage.value = normalizeApiError(error).message;
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  errorMessage.value = "";
  try {
    const payload = {
      user_agent: form.user_agent,
      timeout_seconds: form.timeout_seconds,
      is_active: form.is_active,
      ...(form.api_token ? { api_token: form.api_token } : {}),
    };
    const { data } = await api.patch("/integrations/cosmos/config/", payload);
    applyConfig(data);
    toast.add({ severity: "success", summary: "Configuração Cosmos salva", life: 3000 });
  } catch (error) {
    errorMessage.value = normalizeApiError(error).message;
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.cosmos-page { width: 100%; display: flex; flex-direction: column; gap: 18px; }
.cosmos-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.cosmos-eyebrow { color: var(--text-brand); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: .12em; }
.cosmos-head h1 { margin: 7px 0 5px; color: var(--text-strong); font: var(--weight-extra) 25px/1.15 var(--font-sans); }
.cosmos-head p { margin: 0; color: var(--text-muted); font-size: 13px; }
.cosmos-card { overflow: hidden; display: flex; flex-direction: column; gap: 18px; padding: var(--card-pad); border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.cosmos-card--loading { min-height: 210px; }
.cosmos-section { display: flex; flex-direction: column; gap: 18px; }
.cosmos-section__head { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border-subtle); }
.cosmos-section__head h2 { margin: 0 0 5px; color: var(--text-strong); font-size: 17px; }
.cosmos-section__head p { margin: 0; color: var(--text-muted); font-size: 12px; }
.cosmos-toggle { display: flex; align-items: center; gap: 9px; color: var(--text-body); font: var(--weight-bold) 12px/1 var(--font-sans); }
.cosmos-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.cosmos-field { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.cosmos-field--full { grid-column: 1 / -1; }
.cosmos-field > span { color: var(--text-body); font: var(--weight-bold) 12px/1 var(--font-sans); }
.cosmos-field small { color: var(--text-muted); font-size: 11.5px; line-height: 1.4; }
.cosmos-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding-top: 2px; }
.cosmos-actions a { color: var(--text-brand); font: var(--weight-bold) 12px/1 var(--font-sans); text-decoration: none; }
@media (max-width: 680px) {
  .cosmos-head, .cosmos-section__head, .cosmos-actions { align-items: stretch; flex-direction: column; }
  .cosmos-grid { grid-template-columns: 1fr; }
  .cosmos-field--full { grid-column: auto; }
  .cosmos-actions :deep(.p-button) { width: 100%; }
}
</style>
