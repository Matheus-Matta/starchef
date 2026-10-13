<template>
  <div class="pontos">
    <div class="pontos__row">
      <div>
        <strong>A nuvem também emite</strong>
        <p>
          Com servidor na loja, a nota é emitida pela loja. Ligado, a venda feita
          na nuvem (com a loja fora do ar) também sai com nota, emitida pela nuvem
          numa série só dela. A venda feita na loja continua sendo da loja.
        </p>
      </div>
      <div class="pontos__switch">
        <InputSwitch
          data-test="acbr-cloud-emission"
          :model-value="config.cloud_emission === true"
          @update:model-value="alternar"
        />
        <small>{{ config.cloud_emission ? "Loja e nuvem" : "Só a loja" }}</small>
      </div>
    </div>

    <div v-if="config.cloud_emission" class="pontos__serie">
      <label>
        <span>Série da nuvem</span>
        <InputText
          data-test="acbr-cloud-series"
          type="number"
          min="1"
          :model-value="config.cloud_series ?? ''"
          @update:model-value="(v) => emit('update-field', 'cloud_series', v === '' ? null : Number(v))"
        />
      </label>
      <small>Próximo número na nuvem: {{ config.cloud_next_number ?? 1 }}</small>
      <small v-if="erroDaSerie" data-test="acbr-cloud-series-error" class="pontos__erro">
        {{ erroDaSerie }}
      </small>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";

// Série separada e não contador compartilhado: com a loja sem internet os dois
// lados não se enxergam e repetiriam número (docs/FISCAL_ACBRLIB.md).
const props = defineProps({ config: { type: Object, required: true } });
const emit = defineEmits(["update-field"]);

const erroDaSerie = computed(() => {
  if (!props.config.cloud_emission) return "";
  if (!props.config.cloud_series) return "Informe a série da nuvem.";
  if (Number(props.config.cloud_series) === Number(props.config.series || 1)) {
    return "A série da nuvem precisa ser diferente da série da loja.";
  }
  return "";
});

function alternar(ligado) {
  emit("update-field", "cloud_emission", ligado);
  if (ligado && !props.config.cloud_series) {
    emit("update-field", "cloud_series", Number(props.config.series || 1) + 1);
  }
}
</script>

<style scoped>
.pontos {
  display: grid;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--surface-border, #e5e7eb);
}
.pontos__row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.pontos__row p {
  margin: 4px 0 0;
  color: var(--text-color-secondary, #6b7280);
}
.pontos__switch {
  display: grid;
  justify-items: end;
  gap: 4px;
}
.pontos__serie {
  display: grid;
  gap: 4px;
  max-width: 220px;
}
.pontos__serie label {
  display: grid;
  gap: 4px;
}
.pontos__erro {
  color: var(--red-600, #dc2626);
  font-weight: 600;
}
@media (max-width: 640px) {
  .pontos__row {
    flex-direction: column;
  }
  .pontos__switch {
    justify-items: start;
  }
}
</style>
