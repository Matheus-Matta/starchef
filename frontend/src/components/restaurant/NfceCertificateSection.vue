<template>
  <section class="nfce-cert">
    <header>
      <h2>NFC-e e certificado</h2>
      <p>CSC da NFC-e e certificado A1 usado diretamente nas consultas à SEFAZ.</p>
    </header>

    <div class="nfce-cert__grid">
      <label class="nfce-cert__field">
        <span>ID do CSC (idToken)<b v-if="config.document_model === '65'">*</b></span>
        <InputText :model-value="config.csc_id" placeholder="000001" fluid @update:model-value="update('csc_id', $event)" />
      </label>
      <label class="nfce-cert__field">
        <span>CSC (segredo da NFC-e)<b v-if="config.document_model === '65'">*</b></span>
        <SecretField
          :model-value="config.csc_token"
          :configured="config.csc_token_configured"
          :revealing="revealSecret.csc_token"
          placeholder="Informe o CSC"
          @update:model-value="update('csc_token', $event)"
          @edit="emit('edit-secret', 'csc_token')"
        />
      </label>
      <label v-if="config.provider !== 'focus_nfe'" class="nfce-cert__field">
        <span>Token/credencial do provedor</span>
        <SecretField
          :model-value="config.provider_token"
          :configured="config.provider_token_configured"
          :revealing="revealSecret.provider_token"
          placeholder="Informe a credencial"
          @update:model-value="update('provider_token', $event)"
          @edit="emit('edit-secret', 'provider_token')"
        />
      </label>

      <div class="nfce-cert__field nfce-cert__field--full">
        <span>Certificado A1 para SEFAZ e Focus NFe</span>
        <div class="nfce-cert__status">
          <Tag
            :value="config.has_certificate ? 'Certificado configurado' : 'Certificado pendente'"
            :severity="config.has_certificate ? 'success' : 'warn'"
            rounded
          />
          <small v-if="config.has_certificate">
            {{ config.certificate_name || "A1 armazenado" }}
            <template v-if="config.certificate_valid_until"> · válido até {{ formatDateTime(config.certificate_valid_until) }}</template>
          </small>
        </div>
        <small>Este mesmo A1 busca NF-e recebidas e cadastra ou atualiza a empresa na Focus NFe.</small>
      </div>
      <label class="nfce-cert__field">
        <span>{{ config.has_certificate ? "Substituir certificado A1 (.pfx/.p12)" : "Certificado A1 (.pfx/.p12)" }}</span>
        <input :key="certificateInputKey" class="nfce-cert__file" type="file" accept=".pfx,.p12,application/x-pkcs12" @change="emit('certificate-selected', $event)" />
      </label>
      <label class="nfce-cert__field">
        <span>Senha do certificado A1</span>
        <SecretField
          :model-value="config.certificate_password"
          :configured="config.has_certificate_password"
          :revealing="revealSecret.certificate_password"
          placeholder="Senha do PFX/P12"
          @update:model-value="update('certificate_password', $event)"
          @edit="emit('edit-secret', 'certificate_password')"
        />
      </label>
      <label class="nfce-cert__field">
        <span>Último NSU consultado</span>
        <InputText :model-value="config.dfe_ult_nsu" placeholder="000000000000000" fluid @update:model-value="update('dfe_ult_nsu', $event)" />
        <small>Na primeira configuração, deixe zerado para iniciar a sequência da SEFAZ.</small>
      </label>
      <label class="nfce-cert__field nfce-cert__field--full">
        <span>URL de consulta do QR Code (da UF)</span>
        <InputText :model-value="config.qr_base_url" placeholder="https://..." fluid @update:model-value="update('qr_base_url', $event)" />
      </label>
      <label class="nfce-cert__field nfce-cert__field--full">
        <span>URL do portal de consulta por chave</span>
        <InputText :model-value="config.portal_url" placeholder="https://..." fluid @update:model-value="update('portal_url', $event)" />
      </label>
    </div>
  </section>
</template>

<script setup>
import InputText from "primevue/inputtext";
import Tag from "primevue/tag";

import SecretField from "../form/SecretField.vue";
import { formatDateTime } from "../../utils/format";

defineProps({
  config: { type: Object, required: true },
  revealSecret: { type: Object, required: true },
  certificateInputKey: { type: Number, required: true },
});
const emit = defineEmits(["update-field", "edit-secret", "certificate-selected"]);
const update = (field, value) => emit("update-field", field, value);
</script>

<style scoped>
.nfce-cert { padding: 22px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.nfce-cert header { margin-bottom: 20px; }
.nfce-cert h2 { margin: 0 0 5px; color: var(--text-strong); font-size: 17px; }
.nfce-cert header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.nfce-cert__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.nfce-cert__field { display: flex; min-width: 0; flex-direction: column; gap: 7px; color: var(--text-body); font: var(--weight-bold) 12px/1.2 var(--font-sans); }
.nfce-cert__field--full { grid-column: 1 / -1; }
.nfce-cert__field b { color: #ef4444; margin-left: 3px; }
.nfce-cert__field small { color: var(--text-muted); font-weight: var(--weight-medium); line-height: 1.4; }
.nfce-cert__status { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.nfce-cert__file { width: 100%; min-height: var(--control-h); padding: 8px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-sunken); color: var(--text-body); }
:deep(.p-password), :deep(.p-password-input) { width: 100%; }
@media (max-width: 760px) {
  .nfce-cert__grid { grid-template-columns: 1fr; }
  .nfce-cert__field--full { grid-column: auto; }
}
</style>
