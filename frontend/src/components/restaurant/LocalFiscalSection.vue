<template>
  <section class="local-fiscal">
    <header class="local-fiscal__head">
      <div>
        <span class="local-fiscal__eyebrow">Contingência no terminal</span>
        <h2>Emissão local pelo Comunicador</h2>
        <p>
          O Comunicador da Focus precisa estar instalado e licenciado neste
          terminal antes de ativar este recurso.
        </p>
      </div>
      <span
        data-test="local-fiscal-account-status"
        class="local-fiscal__account-status"
        :class="accountAllows ? 'is-available' : 'is-blocked'"
      >
        <i :class="accountAllows ? 'pi pi-check-circle' : 'pi pi-lock'" />
        {{ accountAllows ? "Disponível para esta conta" : "Bloqueada para esta conta" }}
      </span>
    </header>

    <div v-if="!accountAllows" class="local-fiscal__warning">
      <i class="pi pi-info-circle" />
      <div>
        <strong>Esta conta não autoriza emissão local.</strong>
        <span>Solicite a liberação da conta antes de configurar este terminal.</span>
      </div>
    </div>

    <div class="local-fiscal__body" :class="{ 'is-disabled': !accountAllows }">
      <div class="local-fiscal__activation">
        <div>
          <span class="local-fiscal__label">Ativação</span>
          <strong>Usar o Comunicador neste terminal</strong>
          <p>A nota passa a ser assinada localmente com o certificado da empresa.</p>
        </div>
        <div class="local-fiscal__switch">
          <InputSwitch
            data-test="local-fiscal-enabled"
            :model-value="config.local_fiscal_enabled"
            :disabled="!accountAllows"
            @update:model-value="(v) => emit('update-field', 'local_fiscal_enabled', v)"
          />
          <small>{{ accountAllows ? (config.local_fiscal_enabled ? "Ligada" : "Desligada") : "Indisponível" }}</small>
        </div>
      </div>

      <fieldset class="local-fiscal__mode">
        <legend>Quando usar o Comunicador</legend>
        <p>Escolha uma opção. Para a maioria das lojas, use somente em contingência.</p>
        <div class="local-fiscal__mode-grid">
          <button
            data-test="local-mode-contingency"
            type="button"
            :class="{ 'is-selected': config.local_fiscal_enabled && config.local_fiscal_contingency }"
            :disabled="!accountAllows || !config.local_fiscal_enabled"
            @click="emit('update-field', 'local_fiscal_contingency', true)"
          >
            <span><i class="pi pi-wifi" /> Somente em contingência</span>
            <small>Usa a Focus online e muda para o Comunicador apenas quando o autorizador não responde.</small>
            <em>Recomendado</em>
          </button>
          <button
            data-test="local-mode-always"
            type="button"
            :class="{ 'is-selected': config.local_fiscal_enabled && !config.local_fiscal_contingency }"
            :disabled="!accountAllows || !config.local_fiscal_enabled"
            @click="emit('update-field', 'local_fiscal_contingency', false)"
          >
            <span><i class="pi pi-desktop" /> Sempre pelo Comunicador</span>
            <small>Todas as emissões fiscais deste restaurante passam pelo programa local.</small>
          </button>
        </div>
      </fieldset>

      <label class="local-fiscal__endpoint">
        <span>Endereço do Comunicador neste terminal</span>
        <InputText
          data-test="local-fiscal-url"
          :model-value="config.local_fiscal_url || ''"
          placeholder="http://127.0.0.1:8090"
          :disabled="!accountAllows || !config.local_fiscal_enabled"
          fluid
          @update:model-value="(v) => emit('update-field', 'local_fiscal_url', v)"
        />
        <small>É um endereço local, como o IP de uma impressora. A nuvem não sobrescreve este valor.</small>
      </label>
    </div>
  </section>
</template>

<script setup>
/** Duas travas evitam emissão fiscal real sem liberação e instalação local. */
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";

defineProps({
  config: { type: Object, required: true },
  accountAllows: { type: Boolean, default: false },
});

const emit = defineEmits(["update-field"]);
</script>

<style scoped>
.local-fiscal { padding: var(--card-pad); border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.local-fiscal__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
.local-fiscal__eyebrow { color: var(--text-brand); font: var(--weight-bold) 10px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.local-fiscal h2 { margin: 7px 0 5px; color: var(--text-strong); font-size: 17px; }
.local-fiscal__head p, .local-fiscal__activation p, .local-fiscal__mode > p { margin: 0; color: var(--text-muted); font: var(--weight-medium) 13px/1.45 var(--font-sans); }
.local-fiscal__account-status { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 7px; padding: 8px 10px; border-radius: 999px; font: var(--weight-bold) 11px/1 var(--font-sans); }
.local-fiscal__account-status.is-available { background: color-mix(in srgb, #16a34a 11%, var(--surface-card)); color: #15803d; }
.local-fiscal__account-status.is-blocked { background: var(--surface-sunken); color: var(--text-muted); }
.local-fiscal__warning { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 16px; padding: 12px 14px; border: 1px solid color-mix(in srgb, #f59e0b 35%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, #f59e0b 10%, var(--surface-card)); color: var(--text-body); }
.local-fiscal__warning div { display: grid; gap: 3px; font: var(--weight-medium) 12.5px/1.4 var(--font-sans); }
.local-fiscal__warning i { margin-top: 2px; color: #d97706; }
.local-fiscal__body { display: grid; gap: 18px; }
.local-fiscal__body.is-disabled { opacity: .72; }
.local-fiscal__activation { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 15px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--surface-sunken); }
.local-fiscal__activation > div:first-child { display: grid; gap: 5px; }
.local-fiscal__label { color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.local-fiscal__activation strong { color: var(--text-strong); font-size: 13px; }
.local-fiscal__switch { display: flex; flex: 0 0 auto; align-items: center; gap: 9px; color: var(--text-muted); font-size: 12px; }
.local-fiscal__mode { min-width: 0; margin: 0; padding: 0; border: 0; }
.local-fiscal__mode legend, .local-fiscal__endpoint > span { margin-bottom: 7px; color: var(--text-body); font: var(--weight-bold) 12px/1.2 var(--font-sans); }
.local-fiscal__mode > p { margin-bottom: 10px; font-size: 12px; }
.local-fiscal__mode-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.local-fiscal__mode button { position: relative; display: grid; gap: 8px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body); text-align: left; cursor: pointer; }
.local-fiscal__mode button.is-selected { border-color: var(--brand-border); background: var(--brand-subtle); box-shadow: 0 0 0 1px var(--brand-border); }
.local-fiscal__mode button:disabled { cursor: not-allowed; opacity: .6; }
.local-fiscal__mode button > span { color: var(--text-strong); font: var(--weight-bold) 12.5px/1.2 var(--font-sans); }
.local-fiscal__mode button small, .local-fiscal__endpoint small { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.4 var(--font-sans); }
.local-fiscal__mode button em { width: fit-content; padding: 4px 7px; border-radius: 999px; background: var(--brand); color: white; font: normal var(--weight-bold) 9px/1 var(--font-sans); text-transform: uppercase; }
.local-fiscal__endpoint { display: flex; min-width: 0; flex-direction: column; gap: 7px; }
@media (max-width: 760px) {
  .local-fiscal__head, .local-fiscal__activation { align-items: stretch; flex-direction: column; }
  .local-fiscal__account-status { width: fit-content; }
  .local-fiscal__mode-grid { grid-template-columns: 1fr; }
}
</style>
