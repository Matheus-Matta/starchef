<template>
  <section class="acbr">
    <header class="acbr__head">
      <span class="acbr__eyebrow">Emissor ACBrLib</span>
      <h2>Transmissão pelo comunicador desta instalação</h2>
      <p>
        O servidor (da loja ou da nuvem) assina e transmite a nota pelo comunicador
        ACBrLib dele. O endereço fica no <code>.env</code> do servidor
        (<code>ACBRLIB_URL</code>), porque muda entre a loja e a nuvem.
      </p>
    </header>

    <div class="acbr__row">
      <div>
        <strong>Permitir contingência offline</strong>
        <p>
          Sem resposta da SEFAZ, a NFC-e é assinada em contingência (tpEmis 9), o cupom
          sai e a nota é transmitida sozinha quando a conexão voltar — em até 24 h.
          Recusa da SEFAZ nunca vira contingência.
        </p>
        <p v-if="!isNfce" data-test="acbr-only-nfce" class="acbr__note">
          Só vale para NFC-e (modelo 65).
        </p>
      </div>
      <div class="acbr__switch">
        <InputSwitch
          data-test="acbr-offline-contingency"
          :model-value="config.offline_contingency === true"
          :disabled="!isNfce"
          @update:model-value="(v) => emit('update-field', 'offline_contingency', v)"
        />
        <small>{{ config.offline_contingency && isNfce ? "Ligada" : "Desligada" }}</small>
      </div>
    </div>

    <AcbrPontosDeEmissao :config="config" @update-field="(c, v) => emit('update-field', c, v)" />
  </section>
</template>

<script setup>
import { computed } from "vue";
import InputSwitch from "primevue/inputswitch";

import AcbrPontosDeEmissao from "./AcbrPontosDeEmissao.vue";

// A contingência offline é decisão da empresa (o documento emitido não se
// apaga) e só existe para NFC-e — ver docs/FISCAL_ACBRLIB.md.
const props = defineProps({ config: { type: Object, required: true } });
const emit = defineEmits(["update-field"]);
const isNfce = computed(() => String(props.config.document_model || "65") === "65");
</script>

<style scoped>
.acbr {
  display: grid;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 12px;
  background: var(--surface-card, #fff);
}
.acbr__eyebrow {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--primary-color, #2563eb);
}
.acbr__head h2 {
  margin: 4px 0;
  font-size: 18px;
}
.acbr__head p,
.acbr__row p {
  margin: 4px 0 0;
  color: var(--text-color-secondary, #6b7280);
}
.acbr__row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.acbr__switch {
  display: grid;
  justify-items: end;
  gap: 4px;
}
.acbr__note {
  font-weight: 600;
}
@media (max-width: 640px) {
  .acbr__row {
    flex-direction: column;
  }
  .acbr__switch {
    justify-items: start;
  }
}
</style>
