<template>
  <div class="fs">
    <!-- Mesmo cabeçalho do topo da página (título + subtítulo) — separa
         visualmente os dados do restaurante dos dados fiscais abaixo. -->
    <div class="fs__head">
      <h2>Configuração fiscal</h2>
      <p>{{ readonly ? "Somente leitura." : "Dados e integrador de NF-e/NFC-e deste restaurante. Salva junto com o cadastro." }}</p>
    </div>

    <div v-if="loading" class="fs__hint">Carregando configuração fiscal...</div>

    <div v-else-if="!branchId" class="fs__hint">
      Não foi possível carregar a configuração fiscal deste restaurante. Tente novamente em instantes.
    </div>

    <template v-else>
      <div class="fs__section">
        <div class="fs__grid">
          <div class="fs__field">
            <label for="fs-ie" class="fs__label">Inscrição Estadual</label>
            <InputText id="fs-ie" v-model="form.ie" class="fs__input" :disabled="readonly" />
          </div>
          <div class="fs__field">
            <label for="fs-city_ibge" class="fs__label">Código IBGE do município</label>
            <InputText id="fs-city_ibge" v-model="form.city_ibge" class="fs__input" :disabled="readonly" />
          </div>
        </div>
      </div>

      <div class="fs__section">
        <h3 class="fs__title">Emissão</h3>
        <div class="fs__grid">
          <div class="fs__field">
            <label for="fs-document_model" class="fs__label">Modelo do documento</label>
            <Dropdown id="fs-document_model" v-model="form.document_model" :options="FISCAL_DOCUMENT_MODEL_OPTIONS" option-label="label" option-value="value" class="fs__select" :disabled="readonly" fluid />
          </div>
          <div class="fs__field">
            <label for="fs-environment" class="fs__label">
              Ambiente<span class="fs__required">*</span>
              <i v-tooltip.top="'Comece em Homologação — sem valor fiscal, seguro pra testar o fluxo inteiro.'" class="pi pi-question-circle fs__help-icon" aria-hidden="true" />
            </label>
            <Dropdown id="fs-environment" v-model="form.environment" :options="FISCAL_ENVIRONMENT_OPTIONS" option-label="label" option-value="value" class="fs__select" :disabled="readonly" fluid />
          </div>
          <div class="fs__field">
            <label for="fs-crt" class="fs__label">Regime tributário (CRT)</label>
            <Dropdown id="fs-crt" v-model="form.crt" :options="FISCAL_CRT_OPTIONS" option-label="label" option-value="value" class="fs__select" :disabled="readonly" fluid />
          </div>
          <div class="fs__field">
            <label for="fs-series" class="fs__label">Série</label>
            <InputText id="fs-series" v-model="form.series" type="number" min="1" class="fs__input" :disabled="readonly" />
          </div>
        </div>
      </div>

      <div class="fs__section">
        <h3 class="fs__title">Integração</h3>
        <div class="fs__grid">
          <div v-if="provider !== 'focus_nfe'" class="fs__field">
            <label for="fs-provider_token" class="fs__label">Token/credencial do provedor</label>
            <Password id="fs-provider_token" v-model="form.provider_token" :placeholder="form.provider_token_configured ? '••••••••' : 'Informe a credencial'" :feedback="false" toggle-mask class="fs__password" input-class="fs__input" :disabled="readonly" />
            <small v-if="form.provider_token_configured" class="fs__field-hint">As bolinhas indicam que a credencial já está salva.</small>
          </div>
          <div v-else class="fs__field fs__field--full fs__focus-status">
            <div>
              <span class="fs__label">Empresa na Focus NFe</span>
              <p class="fs__section-desc">{{ focusStatusText }}</p>
              <p v-if="form.focus_sync_error" class="fs__focus-error">{{ form.focus_sync_error }}</p>
            </div>
            <div class="fs__focus-actions">
              <Tag :value="focusStatusLabel" :severity="focusStatusSeverity" rounded />
              <Button v-if="!readonly && configId" label="Sincronizar agora" icon="pi pi-sync" size="small" outlined :loading="focusSyncing" @click="syncFocus" />
            </div>
          </div>
          <div v-if="provider === 'focus_nfe'" class="fs__field">
            <label for="fs-focus-certificate" class="fs__label">Certificado A1 (.pfx/.p12)</label>
            <input id="fs-focus-certificate" class="fs__file" type="file" accept=".pfx,.p12,application/x-pkcs12" :disabled="readonly" @change="onCertificateSelected" />
            <small class="fs__field-hint">Enviado somente para a Focus e removido do StarChef apos sincronizar.</small>
          </div>
          <div v-if="provider === 'focus_nfe'" class="fs__field">
            <label for="fs-focus-certificate-password" class="fs__label">Senha do certificado A1</label>
            <Password id="fs-focus-certificate-password" v-model="form.focus_certificate_password" :placeholder="form.focus_certificate_password_configured ? '••••••••' : 'Senha do PFX/P12'" :feedback="false" toggle-mask class="fs__password" input-class="fs__input" :disabled="readonly" />
            <small v-if="form.focus_certificate_password_configured" class="fs__field-hint">As bolinhas indicam que a senha está salva e aguardando sincronização.</small>
          </div>
          <div class="fs__field">
            <label for="fs-csc_id" class="fs__label">ID do CSC (idToken)</label>
            <InputText id="fs-csc_id" v-model="form.csc_id" class="fs__input" :disabled="readonly" />
          </div>
          <div class="fs__field">
            <label for="fs-csc_token" class="fs__label">CSC (segredo da NFC-e)</label>
            <Password id="fs-csc_token" v-model="form.csc_token" :placeholder="form.csc_token_configured ? '••••••••' : 'Informe o CSC'" :feedback="false" toggle-mask class="fs__password" input-class="fs__input" :disabled="readonly" />
            <small v-if="form.csc_token_configured" class="fs__field-hint">As bolinhas indicam que o CSC já está salvo.</small>
          </div>
          <div class="fs__field">
            <label for="fs-certificate_ref" class="fs__label">Referência do certificado A1</label>
            <InputText id="fs-certificate_ref" v-model="form.certificate_ref" class="fs__input" :disabled="readonly" />
          </div>
          <div class="fs__field fs__field--full">
            <label for="fs-qr_base_url" class="fs__label">URL de consulta do QR Code (da UF)</label>
            <InputText id="fs-qr_base_url" v-model="form.qr_base_url" class="fs__input" :disabled="readonly" />
          </div>
          <div class="fs__field fs__field--full">
            <label for="fs-portal_url" class="fs__label">URL do portal de consulta por chave</label>
            <InputText id="fs-portal_url" v-model="form.portal_url" class="fs__input" :disabled="readonly" />
          </div>
        </div>
        <div v-if="provider === 'focus_nfe' && form.focus_company_dry_run" class="fs__focus-warning">
          <i class="pi pi-info-circle" />
          <span>Simulação ativa na configuração da conta: sincronizar valida os dados, mas não cria nem altera a empresa na Focus.</span>
        </div>
      </div>

      <div v-if="formError" class="fs__alert">
        <i class="pi pi-exclamation-triangle" /> {{ formError }}
      </div>

      <!-- Perfis fiscais NÃO moram mais aqui: são um cadastro da conta,
           reutilizado por qualquer produto de qualquer unidade
           (Financeiro › Perfis fiscais). -->
    </template>
  </div>
</template>

<script setup>
/**
 * Configuração fiscal (FiscalConfig) embutida na página de edição do
 * restaurante — modelo separado no backend (vinculado à filial, um CNPJ por
 * unidade), mas o usuário pensa nisso como "parte do cadastro do
 * restaurante", então mora aqui em vez de um menu à parte.
 *
 * Visual alinhado às seções nativas do formulário (mesmo título + grid dos
 * campos, sem card/fundo próprio) — só o botão de salvar é independente,
 * porque são dois modelos/endpoints diferentes.
 */
import { computed, onMounted, reactive, ref } from "vue";
import Button from "primevue/button";
import Dropdown from "primevue/dropdown";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { useToast } from "primevue/usetoast";

import { ResourceService } from "../../services/ResourceService";
import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { resolveBranchIdForRestaurant } from "../../utils/fiscalBranch";
import {
  FISCAL_CRT_OPTIONS,
  FISCAL_DOCUMENT_MODEL_OPTIONS,
  FISCAL_ENVIRONMENT_OPTIONS,
} from "../../config/enums";

const props = defineProps({
  restaurantId: { type: String, required: true },
  provider: { type: String, default: "manual" },
  readonly: { type: Boolean, default: false },
});

const toast = useToast();
const restaurantService = new ResourceService({ endpoint: "/restaurants/", globalScope: true });
const configService = new ResourceService({ endpoint: "/fiscal/config/", globalScope: true });

const loading = ref(true);
const branchId = ref(null);
const configId = ref(null);
const saving = ref(false);
const focusSyncing = ref(false);
const formError = ref("");
// Guardado só pra ler razão social/CNPJ/endereço na hora de salvar — o
// restaurante é a única fonte desses dados, o form fiscal não os repete.
const restaurant = ref(null);

function emptyForm() {
  return {
    ie: "",
    city_ibge: "",
    document_model: "65",
    environment: "2",
    crt: "1",
    series: 1,
    provider: "manual",
    provider_token: "",
    provider_token_configured: false,
    focus_certificate_base64: "",
    focus_certificate_password: "",
    focus_certificate_configured: false,
    focus_certificate_password_configured: false,
    focus_account_configured: false,
    focus_company_dry_run: false,
    csc_id: "",
    csc_token: "",
    csc_token_configured: false,
    certificate_ref: "",
    qr_base_url: "",
    portal_url: "",
  };
}

const form = reactive(emptyForm());

function onCertificateSelected(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    formError.value = "O certificado deve ter no maximo 5 MB.";
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    form.focus_certificate_base64 = String(reader.result || "").split(",").pop() || "";
  };
  reader.onerror = () => { formError.value = "Nao foi possivel ler o certificado."; };
  reader.readAsDataURL(file);
}

const focusStatusLabel = computed(() => {
  if (form.focus_company_dry_run && !form.focus_company_id) return "Simulação ativa";
  return ({
    synced: "Sincronizado",
    pending: "Sincronizando",
    error: "Erro",
    not_configured: "Nao sincronizado",
  }[form.focus_sync_status] || "Nao sincronizado");
});
const focusStatusSeverity = computed(() => {
  if (form.focus_company_dry_run && !form.focus_company_id) return "info";
  return ({
    synced: "success",
    pending: "warn",
    error: "danger",
  }[form.focus_sync_status] || "secondary");
});
const focusStatusText = computed(() => {
  if (form.focus_company_id) return `Empresa Focus #${form.focus_company_id}`;
  if (form.focus_company_dry_run) return "Os dados podem ser validados, mas a empresa não será criada enquanto a simulação estiver ativa.";
  if (!form.focus_account_configured) return "Configure o Token Principal de Produção da Focus nas configurações da conta.";
  return "A empresa sera criada automaticamente com os dados fiscais deste restaurante.";
});

async function syncFocus() {
  if (!configId.value || focusSyncing.value) return;
  focusSyncing.value = true;
  formError.value = "";
  try {
    const { data } = await api.post(`/fiscal/config/${configId.value}/focus-sync/`, {});
    const syncedConfig = data.config || data;
    Object.assign(form, syncedConfig, {
      provider_token: "",
      csc_token: "",
      focus_certificate_base64: "",
      focus_certificate_password: "",
    });
    const warning = Array.isArray(data.warnings) ? data.warnings.filter(Boolean).join(" ") : "";
    toast.add({
      severity: data.dry_run ? "info" : (data.synced === false || warning ? "warn" : "success"),
      summary: data.dry_run
        ? "Dados validados em simulação"
        : (data.synced === false ? "Empresa não sincronizada" : (warning ? "Empresa sincronizada com aviso" : "Empresa sincronizada com a Focus NFe")),
      detail: [data.message, warning].filter(Boolean).join(" ") || undefined,
      life: data.synced === false || warning ? 6500 : 3000,
    });
  } catch (err) {
    const failedConfig = err?.response?.data?.config;
    if (failedConfig) {
      Object.assign(form, failedConfig, {
        provider_token: "",
        csc_token: "",
        focus_certificate_base64: "",
        focus_certificate_password: "",
      });
    }
    const normalized = normalizeApiError(err);
    formError.value = normalized.message;
    toast.add({ severity: "error", summary: "Falha ao sincronizar com a Focus", detail: normalized.message, life: 7000 });
  } finally {
    focusSyncing.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    const [fetchedRestaurant, resolvedBranchId] = await Promise.all([
      restaurantService.retrieve(props.restaurantId),
      resolveBranchIdForRestaurant(props.restaurantId),
    ]);
    restaurant.value = fetchedRestaurant;
    branchId.value = resolvedBranchId;
    if (!branchId.value) return;

    const configs = await configService.list({ page_size: 200 });
    const existing = (configs.results || []).find((c) => c.restaurant === props.restaurantId);
    if (existing) {
      configId.value = existing.id;
      Object.assign(form, existing, {
        provider_token: "",
        csc_token: "",
        focus_certificate_base64: "",
        focus_certificate_password: "",
      });
    }
  } catch (err) {
    formError.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
});

function buildPayload() {
  const payload = {
    ...form,
    provider: props.provider,
    restaurant: props.restaurantId,
    branch: branchId.value,
    series: Number(form.series) || 1,
    // Razão social/CNPJ/endereço: sempre os dados atuais do restaurante, nunca
    // uma cópia digitada à parte — um só campo pra preencher isso no sistema.
    corporate_name: restaurant.value?.legal_name || restaurant.value?.trade_name || "",
    trade_name: restaurant.value?.trade_name || "",
    cnpj: restaurant.value?.cnpj || "",
    address_line: restaurant.value?.address || "",
    city: restaurant.value?.city || "",
    uf: restaurant.value?.state || "",
    zip_code: restaurant.value?.zip_code || "",
  };
  // Segredos: só manda se o usuário digitou algo novo — em branco significa
  // "não alterar" (mesmo padrão de cash_action_password no cadastro do restaurante).
  if (!payload.provider_token) delete payload.provider_token;
  if (!payload.csc_token) delete payload.csc_token;
  if (!payload.focus_certificate_base64) delete payload.focus_certificate_base64;
  if (!payload.focus_certificate_password) delete payload.focus_certificate_password;
  return payload;
}

/**
 * Chamado pelo botão único do formulário do restaurante (ver
 * ResourceFormView.vue) — não tem botão próprio. Sem filial resolvida ainda
 * não há o que salvar aqui; devolve sucesso pra não travar o salvamento do
 * restaurante. Devolve `false` só quando há mesmo um erro pra corrigir.
 */
async function save() {
  if (!branchId.value) return true;
  saving.value = true;
  formError.value = "";
  try {
    // O formulario principal salva o restaurante antes desta secao. Recarrega
    // para espelhar na configuracao fiscal exatamente os dados recem-gravados.
    restaurant.value = await restaurantService.retrieve(props.restaurantId);
    const payload = buildPayload();
    const saved = configId.value
      ? await configService.update(configId.value, payload)
      : await configService.create(payload);
    configId.value = saved.id;
    Object.assign(form, saved, {
      provider_token: "",
      csc_token: "",
      focus_certificate_base64: "",
      focus_certificate_password: "",
    });
    return true;
  } catch (err) {
    formError.value = normalizeApiError(err).message;
    return false;
  } finally {
    saving.value = false;
  }
}

defineExpose({ save });
</script>

<style scoped>
/* Mesmo tratamento visual das seções nativas do formulário (rpage__section
   em ResourceFormView.vue) — sem card/fundo próprio, só título + grid. */
.fs { display: flex; flex-direction: column; }

/* Mesmo estilo do cabeçalho principal da página (.rpage__card-head). */
.fs__head { padding-top: 18px; padding-bottom: 16px; border-bottom: 1px solid var(--border-subtle); }
.fs__head h2 { color: var(--text-strong); font: var(--weight-extra) 20px/1.2 var(--font-sans); }
.fs__head p { margin-top: 5px; color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); }

.fs__hint {
  padding: 14px 16px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font: var(--weight-medium) 13px/1.4 var(--font-sans);
}

.fs__section { display: flex; flex-direction: column; padding: 22px 0; }
.fs__section + .fs__section { border-top: 1px solid var(--border-subtle); }
.fs__title {
  color: var(--text-strong);
  font: var(--weight-extra) 13px/1.2 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.fs__section-desc { margin-top: 4px; color: var(--text-muted); font: var(--weight-medium) 12.5px/1.4 var(--font-sans); }

.fs__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--field-gap-y) var(--field-gap-x);
  padding-top: 12px;
}
@media (max-width: 760px) {
  .fs__grid { grid-template-columns: 1fr; }
}

.fs__field { display: flex; flex-direction: column; gap: var(--field-label-gap); min-width: 0; }
.fs__field--full { grid-column: 1 / -1; }
.fs__label { display: inline-flex; align-items: center; gap: 5px; color: var(--text-strong); font: var(--weight-bold) 12.5px/1.2 var(--font-sans); letter-spacing: 0.01em; }
.fs__required { color: #ef4444; margin-left: 3px; }
.fs__help-icon { color: var(--text-muted); font-size: 12px; cursor: help; }
.fs__help-icon:hover { color: var(--text-strong); }

.fs__input {
  width: 100%;
  height: var(--control-h);
  padding: 0 var(--control-pad-x);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--text-strong);
  font: var(--weight-medium) var(--control-font)/1 var(--font-sans);
}
.fs__select, .fs__password { width: 100%; }
.fs__file { width: 100%; min-height: var(--control-h); padding: 8px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-sunken); color: var(--text-body); }
.fs__field-hint { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.35 var(--font-sans); }
.fs__focus-status { flex-direction: row; align-items: center; justify-content: space-between; padding: 12px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); }
.fs__focus-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.fs__focus-error { margin-top: 4px; color: #dc2626; font: var(--weight-medium) 12px/1.4 var(--font-sans); }
.fs__focus-warning { display: flex; align-items: flex-start; gap: 9px; margin-top: 12px; padding: 11px 13px; border: 1px solid color-mix(in srgb, #f59e0b 35%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, #f59e0b 10%, var(--surface-card)); color: var(--text-body); font: var(--weight-medium) 12px/1.45 var(--font-sans); }
.fs__focus-warning i { margin-top: 2px; color: #d97706; }

.fs__alert {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  padding: 13px 16px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, #ef4444 9%, var(--surface-card));
  border: 1px solid color-mix(in srgb, #ef4444 24%, transparent);
  color: #dc2626;
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

</style>
