<template>
  <section class="ibscbs">
    <header class="ibscbs__head">
      <span class="ibscbs__eyebrow">Reforma tributária</span>
      <h2>IBS e CBS na nota</h2>
      <p>
        Com isto ligado, cada item leva o CST e o cClassTrib do perfil fiscal do
        produto e os valores de IBS e CBS calculados na emissão. A alíquota vem do
        ano da nota (2026: CBS 0,9%, IBS estadual 0,1%, IBS municipal 0%).
      </p>
    </header>

    <div class="ibscbs__row">
      <div>
        <strong>Enviar IBS/CBS</strong>
        <p>
          Ligue primeiro em Homologação e confira uma nota autorizada antes de ligar
          em Produção. Produto sem CST/cClassTrib no perfil aparece como pendência
          do cadastro.
        </p>
        <p v-if="isSimples" data-test="ibscbs-simples" class="ibscbs__note">
          Simples Nacional não precisa informar IBS/CBS em 2026.
        </p>
      </div>
      <div class="ibscbs__switch">
        <InputSwitch
          data-test="ibscbs-enabled"
          :model-value="config.ibs_cbs_enabled === true"
          @update:model-value="(v) => emit('update-field', 'ibs_cbs_enabled', v)"
        />
        <small>{{ config.ibs_cbs_enabled ? "Ligado" : "Desligado" }}</small>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import InputSwitch from "primevue/inputswitch";

// O flag é da loja e começa desligado: o grupo muda o XML de toda nota, e só a
// homologação confirma o leiaute (docs/FISCAL_IBS_CBS.md).
const props = defineProps({ config: { type: Object, required: true } });
const emit = defineEmits(["update-field"]);
const isSimples = computed(() => ["1", "2"].includes(String(props.config.crt || "1")));
</script>

<style scoped>
.ibscbs {
  display: grid;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 12px;
  background: var(--surface-card, #fff);
}
.ibscbs__eyebrow {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--primary-color, #2563eb);
}
.ibscbs__head h2 {
  margin: 4px 0;
  font-size: 18px;
}
.ibscbs__head p,
.ibscbs__row p {
  margin: 4px 0 0;
  color: var(--text-color-secondary, #6b7280);
}
.ibscbs__row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.ibscbs__switch {
  display: grid;
  justify-items: end;
  gap: 4px;
}
.ibscbs__note {
  font-weight: 600;
}
@media (max-width: 640px) {
  .ibscbs__row {
    flex-direction: column;
  }
  .ibscbs__switch {
    justify-items: start;
  }
}
</style>
