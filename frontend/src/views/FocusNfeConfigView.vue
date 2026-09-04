<template>
  <div class="focus-page">
    <header class="focus-page__head">
      <div>
        <span class="focus-page__eyebrow">Integração fiscal da conta</span>
        <h1>Configuração Focus NFe</h1>
        <p>Estas credenciais valem somente para a conta atual e são usadas por todos os seus restaurantes.</p>
      </div>
      <Button label="Salvar configurações" icon="pi pi-save" :loading="saving" :disabled="loading" @click="save" />
    </header>

    <div v-if="error" class="focus-page__alert">
      <i class="pi pi-exclamation-triangle" /> {{ error }}
    </div>

    <div v-if="loading" class="focus-card focus-card--loading">
      <Skeleton height="44px" />
      <Skeleton height="44px" />
      <Skeleton height="44px" />
    </div>

    <form v-else class="focus-page__form" novalidate @submit.prevent="save">
      <section class="focus-card">
        <div class="focus-card__head">
          <div>
            <h2>Conta integradora</h2>
            <p>Token mestre usado para criar e sincronizar as empresas desta conta.</p>
          </div>
          <Tag
            :value="form.master_token_configured ? 'Token configurado' : 'Token ausente'"
            :severity="form.master_token_configured ? 'success' : 'warning'"
            rounded
          />
        </div>

        <div class="focus-grid">
          <label class="focus-field focus-field--full">
            <span>Token mestre</span>
            <SecretField
              v-model="form.master_token"
              :configured="form.master_token_configured"
              :revealing="revealSecret.master_token"
              placeholder="Informe o token mestre da Focus"
              @edit="startEditingSecret('master_token')"
            />
            <small>Use o Token Principal de Produção da Focus; tokens de emissão não cadastram empresas.</small>
          </label>

          <label class="focus-field">
            <span>URL de produção</span>
            <InputText v-model="form.production_url" class="focus-input" placeholder="https://api.focusnfe.com.br" />
          </label>
          <label class="focus-field">
            <span>URL de homologação</span>
            <InputText v-model="form.homologation_url" class="focus-input" placeholder="https://homologacao.focusnfe.com.br" />
          </label>
          <label class="focus-field">
            <span>Timeout (segundos)</span>
            <InputText v-model.number="form.timeout_seconds" class="focus-input" type="number" min="1" />
          </label>
          <div class="focus-field focus-field--switch">
            <span>Sincronização automática</span>
            <div><InputSwitch v-model="form.auto_sync" /> <small>{{ form.auto_sync ? "Ativa" : "Inativa" }}</small></div>
          </div>
          <div class="focus-field focus-field--switch">
            <span>Simular cadastro da empresa</span>
            <div><InputSwitch v-model="form.company_dry_run" /> <small>{{ form.company_dry_run ? "Dry run ativo" : "Persistir na Focus" }}</small></div>
          </div>
        </div>

        <div v-if="form.company_dry_run" class="focus-page__warning">
          <i class="pi pi-info-circle" />
          <span><strong>Modo de simulação ativo.</strong> A Focus apenas validará os dados; nenhuma empresa será criada ou alterada.</span>
        </div>

        <Button
          v-if="form.master_token_configured"
          type="button"
          label="Remover token mestre"
          icon="pi pi-trash"
          severity="danger"
          text
          :loading="clearing === 'master_token'"
          @click="clearSecret('master_token')"
        />
      </section>

      <section class="focus-card">
        <div class="focus-card__head">
          <div>
            <h2>Webhook</h2>
            <p>Endereço público e segredo usados nas notificações assíncronas da Focus.</p>
          </div>
          <Tag
            :value="form.webhook_authorization_configured ? 'Segredo configurado' : 'Segredo ausente'"
            :severity="form.webhook_authorization_configured ? 'success' : 'warning'"
            rounded
          />
        </div>

        <div class="focus-grid">
          <label class="focus-field focus-field--full">
            <span>URL pública do webhook</span>
            <InputText
              v-model="form.webhook_url"
              class="focus-input"
              placeholder="https://api.seu-dominio.com/api/v1/integrations/focus-nfe/webhook/"
            />
          </label>
          <label class="focus-field">
            <span>Cabeçalho de autorização</span>
            <InputText v-model="form.webhook_authorization_header" class="focus-input" placeholder="Authorization" />
          </label>
          <label class="focus-field">
            <span>Segredo do webhook</span>
            <SecretField
              v-model="form.webhook_authorization"
              :configured="form.webhook_authorization_configured"
              :revealing="revealSecret.webhook_authorization"
              placeholder="Informe um segredo forte"
              @edit="startEditingSecret('webhook_authorization')"
            />
          </label>
        </div>

        <Button
          v-if="form.webhook_authorization_configured"
          type="button"
          label="Remover segredo do webhook"
          icon="pi pi-trash"
          severity="danger"
          text
          :loading="clearing === 'webhook_authorization'"
          @click="clearSecret('webhook_authorization')"
        />
      </section>
    </form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import Button from "primevue/button";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";

import SecretField from "../components/form/SecretField.vue";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const toast = useToast();
const loading = ref(true);
const saving = ref(false);
const clearing = ref("");
const error = ref("");
const form = reactive({
  master_token: "",
  master_token_configured: false,
  production_url: "",
  homologation_url: "",
  timeout_seconds: 30,
  auto_sync: true,
  company_dry_run: false,
  webhook_url: "",
  webhook_authorization: "",
  webhook_authorization_configured: false,
  webhook_authorization_header: "Authorization",
});

// Um segredo em edição mostra o campo real (vazio, pronto para um valor
// novo); fora disso, mostra a máscara com o selo "Salvo" — nunca o
// placeholder sozinho, que fica indistinguível de "vazio" quando focado.
const revealSecret = reactive({ master_token: false, webhook_authorization: false });
function startEditingSecret(field) {
  revealSecret[field] = true;
  form[field] = "";
}

function applyConfig(data) {
  Object.assign(form, data, { master_token: "", webhook_authorization: "" });
  // Toda recarga do servidor é um estado "recém-salvo": volta para a máscara
  // em vez de deixar o campo preso em modo de edição depois de um save.
  revealSecret.master_token = false;
  revealSecret.webhook_authorization = false;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.get("/integrations/focus-nfe/config/");
    applyConfig(data);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const payload = {
      production_url: form.production_url,
      homologation_url: form.homologation_url,
      timeout_seconds: Number(form.timeout_seconds) || 30,
      auto_sync: form.auto_sync,
      company_dry_run: form.company_dry_run,
      webhook_url: form.webhook_url,
      webhook_authorization_header: form.webhook_authorization_header || "Authorization",
      ...(form.master_token ? { master_token: form.master_token } : {}),
      ...(form.webhook_authorization ? { webhook_authorization: form.webhook_authorization } : {}),
    };
    const { data } = await api.patch("/integrations/focus-nfe/config/", payload);
    applyConfig(data);
    toast.add({ severity: "success", summary: "Configuração Focus salva", life: 3000 });
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

async function clearSecret(secret) {
  if (clearing.value) return;
  clearing.value = secret;
  error.value = "";
  try {
    const key = secret === "master_token" ? "clear_master_token" : "clear_webhook_authorization";
    const { data } = await api.patch("/integrations/focus-nfe/config/", { [key]: true });
    applyConfig(data);
    toast.add({ severity: "success", summary: "Credencial removida", life: 2500 });
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    clearing.value = "";
  }
}

onMounted(load);
</script>

<style scoped>
.focus-page { display: flex; flex-direction: column; gap: 18px; max-width: 1060px; margin: 0 auto; }
.focus-page__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.focus-page__eyebrow { color: var(--text-brand); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.focus-page__head h1 { margin: 7px 0 5px; color: var(--text-strong); font-size: 25px; }
.focus-page__head p, .focus-card__head p { margin: 0; color: var(--text-muted); font-size: 13px; }
.focus-page__form { display: flex; flex-direction: column; gap: 18px; }
.focus-card { padding: 22px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.focus-card--loading { display: grid; gap: 14px; }
.focus-card__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.focus-card__head h2 { margin: 0 0 5px; color: var(--text-strong); font-size: 17px; }
.focus-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 12px; }
.focus-field { display: flex; min-width: 0; flex-direction: column; gap: 7px; color: var(--text-body); font: var(--weight-bold) 12px/1.2 var(--font-sans); }
.focus-field--full { grid-column: 1 / -1; }
.focus-field small { color: var(--text-muted); font-weight: var(--weight-medium); }
.focus-field--switch > div { display: flex; align-items: center; gap: 9px; min-height: var(--control-h); }
.focus-input { width: 100%; }
.focus-page__alert { display: flex; align-items: center; gap: 9px; padding: 12px 14px; border: 1px solid var(--danger-border); border-radius: var(--radius-md); background: var(--danger-subtle); color: var(--danger-text); }
.focus-page__warning { display: flex; align-items: flex-start; gap: 9px; margin: 4px 0 12px; padding: 12px 14px; border: 1px solid color-mix(in srgb, #f59e0b 35%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, #f59e0b 10%, var(--surface-card)); color: var(--text-body); font: var(--weight-medium) 12.5px/1.45 var(--font-sans); }
.focus-page__warning i { margin-top: 2px; color: #d97706; }
:deep(.p-password), :deep(.p-password-input) { width: 100%; }
@media (max-width: 720px) {
  .focus-page__head, .focus-card__head { flex-direction: column; }
  .focus-page__head :deep(.p-button) { width: 100%; }
  .focus-grid { grid-template-columns: 1fr; }
  .focus-field--full { grid-column: auto; }
}
</style>
