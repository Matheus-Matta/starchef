<template>
  <div class="fs">
    <!-- Mesmo cabeçalho do topo da página (título + subtítulo) — separa
         visualmente os dados do restaurante dos dados fiscais abaixo. -->
    <div class="fs__head">
      <h2>Configuração fiscal</h2>
      <p>{{ readonly ? "Somente leitura." : "CNPJ e integrador da NFC-e desta filial. Salva junto com o restaurante." }}</p>
    </div>

    <div v-if="loading" class="fs__hint">Carregando configuração fiscal...</div>

    <div v-else-if="!branchId" class="fs__hint">
      Nenhuma filial encontrada para este restaurante — a configuração fiscal fica vinculada à filial.
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
          <div class="fs__field">
            <label for="fs-provider" class="fs__label">
              Provedor de emissão
              <i v-tooltip.top="'Sem conta em um integrador real, deixe em Manual — a nota fica pronta pra impressão mas sem transmitir à SEFAZ.'" class="pi pi-question-circle fs__help-icon" aria-hidden="true" />
            </label>
            <Dropdown id="fs-provider" v-model="form.provider" :options="FISCAL_PROVIDER_OPTIONS" option-label="label" option-value="value" class="fs__select" :disabled="readonly" fluid />
          </div>
          <div class="fs__field">
            <label for="fs-provider_token" class="fs__label">Token/credencial do provedor</label>
            <Password id="fs-provider_token" v-model="form.provider_token" placeholder="Deixe em branco para não alterar" :feedback="false" toggle-mask class="fs__password" input-class="fs__input" :disabled="readonly" />
          </div>
          <div class="fs__field">
            <label for="fs-csc_id" class="fs__label">ID do CSC (idToken)</label>
            <InputText id="fs-csc_id" v-model="form.csc_id" class="fs__input" :disabled="readonly" />
          </div>
          <div class="fs__field">
            <label for="fs-csc_token" class="fs__label">CSC (segredo da NFC-e)</label>
            <Password id="fs-csc_token" v-model="form.csc_token" placeholder="Deixe em branco para não alterar" :feedback="false" toggle-mask class="fs__password" input-class="fs__input" :disabled="readonly" />
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
      </div>

      <div v-if="formError" class="fs__alert">
        <i class="pi pi-exclamation-triangle" /> {{ formError }}
      </div>

      <div class="fs__section">
        <div class="fs__section-head">
          <h3 class="fs__title">Perfis fiscais</h3>
          <Button v-if="!readonly" label="Novo perfil" icon="pi pi-plus" size="small" text @click="openCreateProfile" />
        </div>
        <p class="fs__section-desc">Grupos tributários (NCM/CFOP/CSOSN + alíquotas) reutilizados pelos produtos deste restaurante.</p>

        <div class="fs__profiles">
          <p v-if="!profiles.length" class="fs__hint">Nenhum perfil fiscal cadastrado ainda.</p>
          <div v-for="profile in profiles" :key="profile.id" class="fs__profile-row">
            <div class="fs__profile-info">
              <strong>{{ profile.name }}</strong>
              <span>NCM {{ profile.ncm || "-" }} · CFOP {{ profile.cfop || "-" }}</span>
            </div>
            <Tag v-if="profile.is_default" value="Padrão" severity="info" rounded />
            <Tag :value="profile.is_active ? 'Ativo' : 'Inativo'" :severity="profile.is_active ? 'success' : 'danger'" rounded />
            <div v-if="!readonly" class="fs__profile-actions">
              <Button icon="pi pi-pencil" text rounded aria-label="Editar perfil" @click="openEditProfile(profile)" />
              <Button icon="pi pi-trash" text rounded severity="danger" aria-label="Remover perfil" @click="confirmRemoveProfile(profile)" />
            </div>
          </div>
        </div>
      </div>
    </template>

    <FiscalProfileDialog
      v-if="branchId"
      v-model:visible="profileDialogOpen"
      :restaurant-id="restaurantId"
      :branch-id="branchId"
      :profile="editingProfile"
      @saved="onProfileSaved"
    />
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
import { onMounted, reactive, ref } from "vue";
import Button from "primevue/button";
import Dropdown from "primevue/dropdown";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import Tag from "primevue/tag";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import FiscalProfileDialog from "./FiscalProfileDialog.vue";
import { ResourceService } from "../../services/ResourceService";
import { normalizeApiError } from "../../utils/apiError";
import { resolveBranchIdForRestaurant } from "../../utils/fiscalBranch";
import {
  FISCAL_CRT_OPTIONS,
  FISCAL_DOCUMENT_MODEL_OPTIONS,
  FISCAL_ENVIRONMENT_OPTIONS,
  FISCAL_PROVIDER_OPTIONS,
} from "../../config/enums";

const props = defineProps({
  restaurantId: { type: String, required: true },
  readonly: { type: Boolean, default: false },
});

const toast = useToast();
const confirm = useConfirm();
const restaurantService = new ResourceService({ endpoint: "/restaurants/", globalScope: true });
const configService = new ResourceService({ endpoint: "/fiscal/config/", globalScope: true });
const profileService = new ResourceService({ endpoint: "/fiscal/profiles/", globalScope: true });

const loading = ref(true);
const branchId = ref(null);
const configId = ref(null);
const saving = ref(false);
const formError = ref("");
const profiles = ref([]);
const profileDialogOpen = ref(false);
const editingProfile = ref(null);
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
    csc_id: "",
    csc_token: "",
    certificate_ref: "",
    qr_base_url: "",
    portal_url: "",
  };
}

const form = reactive(emptyForm());

async function loadProfiles() {
  const list = await profileService.list({ page_size: 200 });
  profiles.value = (list.results || []).filter((p) => p.branch === branchId.value);
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
      Object.assign(form, existing, { provider_token: "", csc_token: "" });
    }

    await loadProfiles();
  } catch (err) {
    formError.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
});

function openCreateProfile() {
  editingProfile.value = null;
  profileDialogOpen.value = true;
}
function openEditProfile(profile) {
  editingProfile.value = profile;
  profileDialogOpen.value = true;
}
function onProfileSaved(saved) {
  const index = profiles.value.findIndex((p) => p.id === saved.id);
  if (index >= 0) profiles.value.splice(index, 1, saved);
  else profiles.value.push(saved);
  toast.add({ severity: "success", summary: editingProfile.value ? "Perfil atualizado" : "Perfil adicionado", life: 2500 });
}
function confirmRemoveProfile(profile) {
  confirm.require({
    header: "Remover perfil fiscal?",
    message: `Remover "${profile.name}"? Produtos que usam este perfil passam a usar o perfil padrão da filial.`,
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Remover",
    rejectLabel: "Cancelar",
    acceptClass: "p-button-danger",
    accept: () => removeProfile(profile),
  });
}
async function removeProfile(profile) {
  try {
    await profileService.remove(profile.id);
    profiles.value = profiles.value.filter((p) => p.id !== profile.id);
    toast.add({ severity: "success", summary: "Perfil removido", life: 2000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível remover", detail: normalizeApiError(err).message, life: 4000 });
  }
}

function buildPayload() {
  const payload = {
    ...form,
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
    const payload = buildPayload();
    const saved = configId.value
      ? await configService.update(configId.value, payload)
      : await configService.create(payload);
    configId.value = saved.id;
    Object.assign(form, saved, { provider_token: "", csc_token: "" });
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

.fs__section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.fs__profiles { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; }
.fs__profile-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}
.fs__profile-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.fs__profile-info strong { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.2 var(--font-sans); }
.fs__profile-info span { color: var(--text-muted); font: var(--weight-medium) 12px/1.3 var(--font-sans); }
.fs__profile-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
</style>
