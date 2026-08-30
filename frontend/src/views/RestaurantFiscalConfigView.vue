<template>
  <div class="rfiscal">
    <header class="rfiscal__head">
      <div class="rfiscal__crumbs">
        <button class="rfiscal__back" type="button" @click="goToList">
          <i class="pi pi-arrow-left" />
          <span>Restaurantes</span>
        </button>
        <i class="pi pi-chevron-right rfiscal__sep" />
        <span class="rfiscal__crumb">{{ restaurantName || "Restaurante" }}</span>
        <i class="pi pi-chevron-right rfiscal__sep" />
        <span class="rfiscal__crumb">Configuração fiscal</span>
      </div>

      <div class="rfiscal__head-actions">
        <Button label="Abrir cadastro" icon="pi pi-building" severity="secondary" outlined @click="goToRestaurant" />
        <Button label="Salvar configuração" icon="pi pi-save" :loading="saving" :disabled="loading || !configId" @click="save" />
      </div>
    </header>

    <div class="rfiscal__title">
      <div>
        <span class="rfiscal__eyebrow">Emissão fiscal desta unidade</span>
        <h1>Configuração fiscal — {{ restaurantName || "…" }}</h1>
        <p>
          Emitente, parâmetros de emissão e integração com a Focus NFe. É um cadastro próprio,
          separado dos dados comerciais do restaurante.
        </p>
      </div>
      <div class="rfiscal__title-tags">
        <Tag :value="providerLabel" :severity="form.provider === 'focus_nfe' ? 'info' : 'secondary'" rounded />
        <Tag v-if="form.provider === 'focus_nfe'" :value="focusStatusLabel" :severity="focusStatusSeverity" rounded />
      </div>
    </div>

    <div v-if="error" class="rfiscal__alert rfiscal__alert--error">
      <i class="pi pi-exclamation-triangle" /> {{ error }}
    </div>

    <div v-if="loading" class="rfiscal__card rfiscal__card--loading">
      <Skeleton height="44px" />
      <Skeleton height="44px" />
      <Skeleton height="44px" />
    </div>

    <form v-else-if="configId" class="rfiscal__form" novalidate @submit.prevent="save">
      <!-- Pendências: exatamente o que a Focus recusaria, mostrado ANTES de sincronizar. -->
      <div v-if="missingFields.length" class="rfiscal__alert rfiscal__alert--warn">
        <i class="pi pi-exclamation-circle" />
        <div>
          <strong>Faltam dados obrigatórios para emitir/sincronizar:</strong>
          {{ missingFields.map((item) => item.message || item.label).join(" ") }}
          <span class="rfiscal__alert-hint">Preencha em "Dados do emitente", abaixo, e salve.</span>
        </div>
      </div>

      <section class="rfiscal__card">
        <div class="rfiscal__card-head">
          <div>
            <h2>Provedor de emissão</h2>
            <p>Quem transmite a nota à SEFAZ. As credenciais da Focus são da conta inteira.</p>
          </div>
          <Button
            label="Credenciais da conta Focus"
            icon="pi pi-external-link"
            severity="secondary"
            text
            @click="goToAccountFocus"
          />
        </div>
        <div class="rfiscal__grid">
          <label class="rfiscal__field rfiscal__field--full">
            <span>Provedor</span>
            <Dropdown
              v-model="form.provider"
              :options="FISCAL_PROVIDER_OPTIONS"
              option-label="label"
              option-value="value"
              fluid
            />
            <small>
              Focus NFe cria e sincroniza a empresa e transmite NF-e/NFC-e pela API.
              Manual apenas monta o documento, sem transmissão.
            </small>
          </label>
        </div>
        <div v-if="form.provider === 'focus_nfe' && !form.focus_account_configured" class="rfiscal__inline-warning">
          <i class="pi pi-info-circle" />
          <span>
            A conta ainda não tem o Token Principal de Produção da Focus.
            Configure em <strong>Credenciais da conta Focus</strong> antes de sincronizar.
          </span>
        </div>
      </section>

      <section class="rfiscal__card">
        <div class="rfiscal__card-head">
          <div>
            <h2>Dados do emitente</h2>
            <p>É o que vai na nota. Nasce espelhado do cadastro do restaurante e a partir daí é editável aqui.</p>
          </div>
          <Button
            label="Copiar do cadastro"
            icon="pi pi-copy"
            severity="secondary"
            outlined
            :disabled="!restaurant"
            @click="copyFromRestaurant"
          />
        </div>
        <div class="rfiscal__grid">
          <label class="rfiscal__field rfiscal__field--full">
            <span>Razão social<b>*</b></span>
            <InputText v-model="form.corporate_name" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Nome fantasia</span>
            <InputText v-model="form.trade_name" fluid />
          </label>
          <label class="rfiscal__field">
            <span>CNPJ<b>*</b></span>
            <InputText v-model="form.cnpj" placeholder="00.000.000/0000-00" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Inscrição Estadual<b>*</b></span>
            <InputText v-model="form.ie" placeholder="Somente números ou ISENTO" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Código IBGE do município</span>
            <InputText v-model="form.city_ibge" placeholder="3550308" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Logradouro<b>*</b></span>
            <InputText v-model="form.address_line" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Número<b>*</b></span>
            <InputText v-model="form.address_number" placeholder="Ex.: 123 ou S/N" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Cidade<b>*</b></span>
            <InputText v-model="form.city" fluid />
          </label>
          <label class="rfiscal__field">
            <span>UF<b>*</b></span>
            <InputText v-model="form.uf" maxlength="2" placeholder="SP" fluid />
          </label>
          <label class="rfiscal__field">
            <span>CEP<b>*</b></span>
            <InputText v-model="form.zip_code" placeholder="00000-000" fluid />
          </label>
        </div>
      </section>

      <section class="rfiscal__card">
        <div class="rfiscal__card-head">
          <div>
            <h2>Parâmetros de emissão</h2>
            <p>Comece em Homologação: sem valor fiscal, seguro para testar o fluxo inteiro.</p>
          </div>
        </div>
        <div class="rfiscal__grid">
          <label class="rfiscal__field">
            <span>Modelo do documento</span>
            <Dropdown v-model="form.document_model" :options="FISCAL_DOCUMENT_MODEL_OPTIONS" option-label="label" option-value="value" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Ambiente</span>
            <Dropdown v-model="form.environment" :options="FISCAL_ENVIRONMENT_OPTIONS" option-label="label" option-value="value" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Regime tributário (CRT)</span>
            <Dropdown v-model="form.crt" :options="FISCAL_CRT_OPTIONS" option-label="label" option-value="value" fluid />
          </label>
          <label class="rfiscal__field">
            <span>Série</span>
            <InputText v-model="form.series" type="number" min="1" fluid />
          </label>
          <div class="rfiscal__field">
            <span>Próximo número (nNF)</span>
            <InputText :model-value="String(form.next_number ?? 1)" disabled fluid />
            <small>Sequencial gerido pelo sistema a cada nota emitida.</small>
          </div>
          <div class="rfiscal__field rfiscal__field--switch">
            <span>Configuração ativa</span>
            <div><InputSwitch v-model="form.is_active" /> <small>{{ form.is_active ? "Ativa" : "Inativa" }}</small></div>
          </div>
        </div>
      </section>

      <section class="rfiscal__card">
        <div class="rfiscal__card-head">
          <div>
            <h2>NFC-e e certificado</h2>
            <p>CSC emitido pela SEFAZ da UF e URLs de consulta impressas no cupom.</p>
          </div>
        </div>
        <div class="rfiscal__grid">
          <label class="rfiscal__field">
            <span>ID do CSC (idToken)<b v-if="form.document_model === '65'">*</b></span>
            <InputText v-model="form.csc_id" placeholder="000001" fluid />
          </label>
          <label class="rfiscal__field">
            <span>CSC (segredo da NFC-e)<b v-if="form.document_model === '65'">*</b></span>
            <SecretField
              v-model="form.csc_token"
              :configured="form.csc_token_configured"
              :revealing="revealSecret.csc_token"
              placeholder="Informe o CSC"
              @edit="startEditingSecret('csc_token')"
            />
          </label>
          <label v-if="form.provider !== 'focus_nfe'" class="rfiscal__field">
            <span>Token/credencial do provedor</span>
            <SecretField
              v-model="form.provider_token"
              :configured="form.provider_token_configured"
              :revealing="revealSecret.provider_token"
              placeholder="Informe a credencial"
              @edit="startEditingSecret('provider_token')"
            />
          </label>
          <label class="rfiscal__field">
            <span>Referência do certificado A1</span>
            <InputText v-model="form.certificate_ref" fluid />
          </label>
          <label class="rfiscal__field rfiscal__field--full">
            <span>URL de consulta do QR Code (da UF)</span>
            <InputText v-model="form.qr_base_url" placeholder="https://..." fluid />
          </label>
          <label class="rfiscal__field rfiscal__field--full">
            <span>URL do portal de consulta por chave</span>
            <InputText v-model="form.portal_url" placeholder="https://..." fluid />
          </label>
        </div>
      </section>

      <section v-if="form.provider === 'focus_nfe'" class="rfiscal__card">
        <div class="rfiscal__card-head">
          <div>
            <h2>Empresa na Focus NFe</h2>
            <p>{{ focusStatusText }}</p>
          </div>
          <Tag :value="focusStatusLabel" :severity="focusStatusSeverity" rounded />
        </div>

        <dl class="rfiscal__facts">
          <div><dt>Empresa</dt><dd>{{ form.focus_company_id ? `#${form.focus_company_id}` : "Ainda não criada" }}</dd></div>
          <div><dt>Última sincronização</dt><dd>{{ syncedAtLabel }}</dd></div>
          <div><dt>Token de emissão</dt><dd>{{ form.focus_connected ? "Recebido da Focus" : "Pendente" }}</dd></div>
        </dl>

        <div v-if="form.focus_sync_error" class="rfiscal__alert rfiscal__alert--error rfiscal__alert--inline">
          <i class="pi pi-times-circle" /> {{ form.focus_sync_error }}
        </div>

        <div v-if="form.focus_company_dry_run" class="rfiscal__inline-warning">
          <i class="pi pi-info-circle" />
          <span>
            <strong>Simulação (dry run) ativa na conta.</strong>
            Sincronizar apenas valida os dados; nenhuma empresa é criada ou alterada na Focus.
          </span>
        </div>

        <div class="rfiscal__grid rfiscal__grid--spaced">
          <label class="rfiscal__field">
            <span>Certificado A1 (.pfx/.p12)</span>
            <input class="rfiscal__file" type="file" accept=".pfx,.p12,application/x-pkcs12" @change="onCertificateSelected" />
            <small>Enviado somente à Focus e descartado do StarChef assim que a empresa sincroniza.</small>
          </label>
          <label class="rfiscal__field">
            <span>Senha do certificado A1</span>
            <SecretField
              v-model="form.focus_certificate_password"
              :configured="form.focus_certificate_password_configured"
              :revealing="revealSecret.focus_certificate_password"
              placeholder="Senha do PFX/P12"
              @edit="startEditingSecret('focus_certificate_password')"
            />
            <small>Certificado e senha viajam sempre juntos, na mesma gravação.</small>
          </label>
        </div>

        <div class="rfiscal__actions">
          <Button label="Sincronizar agora" icon="pi pi-sync" :loading="busy === 'sync'" :disabled="!!busy" @click="runFocus('focus-sync')" />
          <Button label="Atualizar status" icon="pi pi-refresh" severity="secondary" outlined :loading="busy === 'refresh'" :disabled="!!busy" @click="runFocus('focus-refresh')" />
          <Button
            v-if="form.focus_company_id"
            label="Excluir empresa na Focus"
            icon="pi pi-trash"
            severity="danger"
            text
            :disabled="!!busy"
            @click="deleteDialog = true"
          />
        </div>
        <p class="rfiscal__actions-hint">
          "Sincronizar agora" salva a configuração antes de enviar — a Focus recebe exatamente o que está gravado aqui.
        </p>
      </section>
    </form>

    <Dialog v-model:visible="deleteDialog" modal header="Excluir empresa na Focus NFe" :style="{ width: '440px' }">
      <p class="rfiscal__dialog-text">
        Isso remove a empresa na Focus e descarta os tokens de emissão desta unidade.
        Para confirmar, digite o CNPJ completo do emitente.
      </p>
      <InputText v-model="deleteConfirmCnpj" placeholder="00.000.000/0000-00" fluid />
      <template #footer>
        <Button label="Cancelar" severity="secondary" text @click="deleteDialog = false" />
        <Button label="Excluir empresa" severity="danger" :loading="busy === 'delete'" @click="deleteCompany" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
/**
 * Configuração fiscal avançada de UM restaurante (FiscalConfig).
 *
 * Vive fora do formulário do restaurante de propósito: são dois modelos e dois
 * endpoints, e enquanto os dois salvavam juntos o POST desta configuração corria
 * com o cadastro do restaurante na mesma `unique_fiscal_config_by_branch` — o
 * "Já existe um registro com estes dados (valor duplicado)" que travava o
 * cadastro. Aqui a configuração é sempre carregada (e criada, se preciso) pelo
 * endpoint `for-restaurant`; daí em diante só existe PATCH.
 */
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import Dropdown from "primevue/dropdown";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";

import SecretField from "../components/form/SecretField.vue";
import { api } from "../services/api";
import { ResourceService } from "../services/ResourceService";
import { normalizeApiError } from "../utils/apiError";
import { formatDateTime } from "../utils/format";
import {
  FISCAL_CRT_OPTIONS,
  FISCAL_DOCUMENT_MODEL_OPTIONS,
  FISCAL_ENVIRONMENT_OPTIONS,
  FISCAL_PROVIDER_OPTIONS,
} from "../config/enums";

const props = defineProps({ id: { type: String, required: true } });

const router = useRouter();
const toast = useToast();
const restaurantService = new ResourceService({ endpoint: "/restaurants/", globalScope: true });

const loading = ref(true);
const saving = ref(false);
const busy = ref("");
const error = ref("");
const configId = ref(null);
const restaurant = ref(null);
const deleteDialog = ref(false);
const deleteConfirmCnpj = ref("");

// Um segredo em edição mostra o campo real (vazio, pronto para um valor
// novo); fora disso, mostra a máscara com o selo "Salvo" — nunca o
// placeholder sozinho, que fica indistinguível de "vazio" quando focado.
const revealSecret = reactive({
  csc_token: false,
  provider_token: false,
  focus_certificate_password: false,
});
function startEditingSecret(field) {
  revealSecret[field] = true;
  form[field] = "";
}

// Só o que esta tela edita — o resto da resposta (tokens, status de
// sincronização, auditoria) fica fora do PATCH de propósito.
const EDITABLE_FIELDS = [
  "provider", "document_model", "environment", "crt", "series", "is_active",
  "corporate_name", "trade_name", "cnpj", "ie", "address_line", "address_number", "city", "city_ibge", "uf", "zip_code",
  "csc_id", "qr_base_url", "portal_url", "certificate_ref",
];
// Em branco significa "não alterar" — o GET nunca devolve segredo.
const SECRET_FIELDS = ["csc_token", "provider_token", "focus_certificate_base64", "focus_certificate_password"];

const form = reactive({
  provider: "manual",
  document_model: "65",
  environment: "2",
  crt: "1",
  series: 1,
  next_number: 1,
  is_active: true,
  corporate_name: "",
  trade_name: "",
  cnpj: "",
  ie: "",
  address_line: "",
  address_number: "",
  city: "",
  city_ibge: "",
  uf: "",
  zip_code: "",
  csc_id: "",
  csc_token: "",
  csc_token_configured: false,
  provider_token: "",
  provider_token_configured: false,
  qr_base_url: "",
  portal_url: "",
  certificate_ref: "",
  focus_certificate_base64: "",
  focus_certificate_password: "",
  focus_certificate_password_configured: false,
  focus_company_id: "",
  focus_connected: false,
  focus_sync_status: "not_configured",
  focus_sync_error: "",
  focus_synced_at: null,
  focus_account_configured: false,
  focus_company_dry_run: false,
  focus_missing_fields: [],
});

const restaurantName = computed(() => restaurant.value?.trade_name || form.trade_name || "");
const missingFields = computed(() => form.focus_missing_fields || []);
const providerLabel = computed(
  () => FISCAL_PROVIDER_OPTIONS.find((option) => option.value === form.provider)?.label || form.provider,
);
const syncedAtLabel = computed(() => (form.focus_synced_at ? formatDateTime(form.focus_synced_at) : "Nunca"));

const focusStatusLabel = computed(() => {
  if (form.focus_company_dry_run && !form.focus_company_id) return "Simulação ativa";
  return ({
    synced: "Sincronizado",
    pending: "Sincronizando",
    error: "Erro",
    not_configured: "Não sincronizado",
  }[form.focus_sync_status] || "Não sincronizado");
});
const focusStatusSeverity = computed(() => {
  if (form.focus_company_dry_run && !form.focus_company_id) return "info";
  return ({ synced: "success", pending: "warn", error: "danger" }[form.focus_sync_status] || "secondary");
});
const focusStatusText = computed(() => {
  if (form.focus_company_id) return `Empresa #${form.focus_company_id} vinculada a esta unidade na Focus NFe.`;
  if (!form.focus_account_configured) return "Configure o Token Principal de Produção da conta antes de sincronizar.";
  if (missingFields.value.length) return "Complete os dados do emitente para que a Focus aceite a empresa.";
  return "A empresa será criada na Focus com os dados desta configuração.";
});

/** Aplica a resposta da API sem reintroduzir segredos (que voltam sempre vazios). */
function applyConfig(data) {
  Object.assign(form, data);
  for (const field of SECRET_FIELDS) form[field] = "";
  configId.value = data.id || configId.value;
  // Toda recarga do servidor é um estado "recém-salvo": volta para a máscara
  // em vez de deixar o campo preso em modo de edição depois de um save.
  for (const field of Object.keys(revealSecret)) revealSecret[field] = false;
}

function onCertificateSelected(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    error.value = "O certificado deve ter no máximo 5 MB.";
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => { form.focus_certificate_base64 = String(reader.result || "").split(",").pop() || ""; };
  reader.onerror = () => { error.value = "Não foi possível ler o certificado."; };
  reader.readAsDataURL(file);
}

function copyFromRestaurant() {
  const source = restaurant.value;
  if (!source) return;
  form.corporate_name = source.legal_name || source.trade_name || "";
  form.trade_name = source.trade_name || "";
  form.cnpj = source.cnpj || "";
  form.ie = source.state_registration || "";
  const address = String(source.address || "").trim();
  const addressParts = address.match(/^(.*?),\s*([0-9][^,]*)$/);
  form.address_line = addressParts?.[1]?.trim() || address;
  form.address_number = addressParts?.[2]?.trim() || form.address_number || "";
  form.city = source.city || "";
  form.uf = source.state || "";
  form.zip_code = source.zip_code || "";
  toast.add({ severity: "info", summary: "Dados copiados do cadastro", detail: "Revise e salve para gravar.", life: 3000 });
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [fetchedRestaurant, response] = await Promise.all([
      restaurantService.retrieve(props.id),
      api.get("/fiscal/config/for-restaurant/", { params: { restaurant: props.id }, skipRestaurantScope: true }),
    ]);
    restaurant.value = fetchedRestaurant;
    applyConfig(response.data);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
}

function buildPayload() {
  const payload = {};
  for (const field of EDITABLE_FIELDS) payload[field] = form[field];
  payload.series = Number(form.series) || 1;
  payload.uf = (form.uf || "").toUpperCase();
  for (const field of SECRET_FIELDS) {
    if (form[field]) payload[field] = form[field];
  }
  return payload;
}

async function save() {
  if (saving.value || !configId.value) return false;
  saving.value = true;
  error.value = "";
  try {
    const { data } = await api.patch(`/fiscal/config/${configId.value}/`, buildPayload());
    applyConfig(data);
    toast.add({ severity: "success", summary: "Configuração fiscal salva", life: 3000 });
    return true;
  } catch (err) {
    error.value = normalizeApiError(err).message;
    toast.add({ severity: "error", summary: "Não foi possível salvar", detail: error.value, life: 6000 });
    return false;
  } finally {
    saving.value = false;
  }
}

/** Sincroniza/atualiza a empresa na Focus. Salva antes: a Focus lê o que está gravado. */
async function runFocus(action) {
  if (busy.value) return;
  if (action === "focus-sync" && !(await save())) return;
  busy.value = action === "focus-sync" ? "sync" : "refresh";
  error.value = "";
  try {
    const { data } = await api.post(`/fiscal/config/${configId.value}/${action}/`, {});
    applyConfig(data.config || data);
    const warning = Array.isArray(data.warnings) ? data.warnings.filter(Boolean).join(" ") : "";
    toast.add({
      severity: data.dry_run ? "info" : (data.synced === false || warning ? "warn" : "success"),
      summary: data.dry_run
        ? "Dados validados em simulação"
        : (data.synced === false ? "Empresa não sincronizada" : (warning ? "Sincronizada com aviso" : "Empresa sincronizada com a Focus NFe")),
      detail: [data.message, warning].filter(Boolean).join(" ") || undefined,
      life: data.synced === false || warning ? 6500 : 3000,
    });
  } catch (err) {
    const failed = err?.response?.data?.config;
    if (failed) applyConfig(failed);
    error.value = normalizeApiError(err).message;
    toast.add({ severity: "error", summary: "Falha na comunicação com a Focus", detail: error.value, life: 7000 });
  } finally {
    busy.value = "";
  }
}

async function deleteCompany() {
  if (busy.value) return;
  busy.value = "delete";
  error.value = "";
  try {
    const { data } = await api.delete(`/fiscal/config/${configId.value}/focus-company/`, {
      data: { confirm_cnpj: deleteConfirmCnpj.value },
    });
    applyConfig(data.config || data);
    deleteDialog.value = false;
    deleteConfirmCnpj.value = "";
    toast.add({ severity: "success", summary: "Empresa removida da Focus", life: 3000 });
  } catch (err) {
    error.value = normalizeApiError(err).message;
    toast.add({ severity: "error", summary: "Não foi possível excluir", detail: error.value, life: 6000 });
  } finally {
    busy.value = "";
  }
}

function goToList() {
  router.push({ name: "restaurantes" });
}
function goToRestaurant() {
  router.push({ name: "restaurantes--view", params: { id: props.id } });
}
function goToAccountFocus() {
  router.push({ name: "configuracao-focus" });
}

onMounted(load);
</script>

<style scoped>
.rfiscal { display: flex; flex-direction: column; gap: 18px; max-width: 1060px; margin: 0 auto; }

.rfiscal__head { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.rfiscal__crumbs { display: flex; align-items: center; gap: 8px; min-width: 0; flex-wrap: wrap; }
.rfiscal__back {
  display: inline-flex; align-items: center; gap: 7px; padding: 0; border: 0; background: none;
  color: var(--text-brand); font: var(--weight-bold) 13px/1 var(--font-sans); cursor: pointer;
}
.rfiscal__sep, .rfiscal__crumb { color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); }
.rfiscal__head-actions { display: inline-flex; gap: 8px; flex-wrap: wrap; }

.rfiscal__title { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
.rfiscal__eyebrow { color: var(--text-brand); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.rfiscal__title h1 { margin: 7px 0 5px; color: var(--text-strong); font-size: 25px; }
.rfiscal__title p { margin: 0; max-width: 62ch; color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); }
.rfiscal__title-tags { display: inline-flex; gap: 8px; flex-wrap: wrap; }

.rfiscal__form { display: flex; flex-direction: column; gap: 18px; }
.rfiscal__card { padding: 22px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.rfiscal__card--loading { display: grid; gap: 14px; }
.rfiscal__card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.rfiscal__card-head h2 { margin: 0 0 5px; color: var(--text-strong); font-size: 17px; }
.rfiscal__card-head p { margin: 0; max-width: 62ch; color: var(--text-muted); font-size: 13px; }

.rfiscal__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.rfiscal__grid--spaced { margin-top: 18px; }
.rfiscal__field { display: flex; min-width: 0; flex-direction: column; gap: 7px; color: var(--text-body); font: var(--weight-bold) 12px/1.2 var(--font-sans); }
.rfiscal__field--full { grid-column: 1 / -1; }
.rfiscal__field b { color: #ef4444; margin-left: 3px; }
.rfiscal__field small { color: var(--text-muted); font-weight: var(--weight-medium); line-height: 1.4; }
.rfiscal__field--switch > div { display: flex; align-items: center; gap: 9px; min-height: var(--control-h); }
.rfiscal__file { width: 100%; min-height: var(--control-h); padding: 8px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-sunken); color: var(--text-body); }
.rfiscal__input { width: 100%; }

.rfiscal__facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 0 0 18px; }
.rfiscal__facts div { padding: 12px 14px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--surface-sunken); }
.rfiscal__facts dt { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.rfiscal__facts dd { margin: 6px 0 0; color: var(--text-strong); font: var(--weight-semibold) 13.5px/1.3 var(--font-sans); }

.rfiscal__actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
.rfiscal__actions-hint { margin: 10px 0 0; color: var(--text-muted); font: var(--weight-medium) 12px/1.4 var(--font-sans); }

.rfiscal__alert { display: flex; align-items: flex-start; gap: 10px; padding: 13px 15px; border-radius: var(--radius-md); font: var(--weight-semibold) 13px/1.45 var(--font-sans); }
.rfiscal__alert i { margin-top: 1px; }
.rfiscal__alert--error { border: 1px solid color-mix(in srgb, #ef4444 24%, transparent); background: color-mix(in srgb, #ef4444 9%, var(--surface-card)); color: #dc2626; }
.rfiscal__alert--warn { border: 1px solid color-mix(in srgb, #f59e0b 35%, transparent); background: color-mix(in srgb, #f59e0b 10%, var(--surface-card)); color: var(--text-body); }
.rfiscal__alert--inline { margin-bottom: 16px; }
.rfiscal__alert-hint { display: block; margin-top: 3px; font-weight: var(--weight-medium); color: var(--text-muted); }

.rfiscal__inline-warning { display: flex; align-items: flex-start; gap: 9px; margin-top: 16px; padding: 11px 13px; border: 1px solid color-mix(in srgb, #f59e0b 35%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, #f59e0b 10%, var(--surface-card)); color: var(--text-body); font: var(--weight-medium) 12.5px/1.45 var(--font-sans); }
.rfiscal__inline-warning i { margin-top: 2px; color: #d97706; }

.rfiscal__dialog-text { margin: 0 0 14px; color: var(--text-body); font: var(--weight-medium) 13px/1.5 var(--font-sans); }

:deep(.p-password), :deep(.p-password-input) { width: 100%; }

@media (max-width: 760px) {
  .rfiscal__grid, .rfiscal__facts { grid-template-columns: 1fr; }
  .rfiscal__field--full { grid-column: auto; }
  .rfiscal__card-head { flex-direction: column; }
  .rfiscal__head-actions :deep(.p-button) { flex: 1 1 auto; }
}
</style>
