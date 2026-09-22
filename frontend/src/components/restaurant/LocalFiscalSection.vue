<template>
  <section class="rfiscal__card">
    <div class="rfiscal__card-head">
      <h2>Emissão local (contingência)</h2>
      <p>
        Quando a loja não alcança o autorizador, o Comunicador da Focus emite a
        NFC-e aqui mesmo e a transmite quando a conexão voltar. Ele é um
        programa que roda <strong>no terminal</strong>, e precisa estar
        instalado e licenciado antes de ligar isto.
      </p>
    </div>

    <div v-if="!accountAllows" class="rfiscal__aviso">
      Esta conta não autoriza emissão local. Enquanto isso não mudar, os campos
      abaixo ficam desligados — é a trava de cima, e ela existe para não
      depender de alguém lembrar de conferir a de baixo.
    </div>

    <div class="rfiscal__grid">
      <div class="rfiscal__field rfiscal__field--switch">
        <span>Emissão local ligada</span>
        <div>
          <InputSwitch
            :model-value="config.local_fiscal_enabled"
            :disabled="!accountAllows"
            @update:model-value="(v) => emit('update-field', 'local_fiscal_enabled', v)"
          />
          <small>{{ config.local_fiscal_enabled ? "Ligada" : "Desligada" }}</small>
        </div>
      </div>

      <div class="rfiscal__field rfiscal__field--switch">
        <span>Só em contingência</span>
        <div>
          <InputSwitch
            :model-value="config.local_fiscal_contingency"
            :disabled="!accountAllows || !config.local_fiscal_enabled"
            @update:model-value="(v) => emit('update-field', 'local_fiscal_contingency', v)"
          />
          <small>
            {{ config.local_fiscal_contingency
              ? "Só quando o autorizador não responde"
              : "Sempre pelo Comunicador" }}
          </small>
        </div>
      </div>

      <label class="rfiscal__field rfiscal__field--wide">
        <span>Endereço do Comunicador</span>
        <InputText
          data-test="local-fiscal-url"
          :model-value="config.local_fiscal_url || ''"
          placeholder="http://127.0.0.1:55555"
          :disabled="!accountAllows || !config.local_fiscal_enabled"
          fluid
          @update:model-value="(v) => emit('update-field', 'local_fiscal_url', v)"
        />
        <small>
          Onde o Comunicador escuta <strong>neste terminal</strong>. É como o IP
          da impressora: cada loja tem o seu, e por isso este campo nunca é
          sobrescrito pela nuvem.
        </small>
      </label>
    </div>
  </section>
</template>

<script setup>
/**
 * As três chaves da emissão fiscal local.
 *
 * Elas já existiam no cadastro e no serializer; o que faltava era a tela — sem
 * ela, ligar a contingência dependia do admin do Django, e o endereço do
 * Comunicador não tinha onde ser digitado pelo técnico que instala a loja.
 *
 * Um terminal que liga isto sozinho passa a assinar NFC-e REAIS com o
 * certificado da empresa, e documento fiscal emitido não se apaga: só se
 * cancela, um a um, dentro do prazo. Por isso são DUAS travas — a conta
 * autoriza e a loja liga — e por isso os campos aparecem desabilitados, com o
 * motivo à vista, em vez de simplesmente sumirem.
 */
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";

defineProps({
  config: { type: Object, required: true },
  accountAllows: { type: Boolean, default: false },
});

const emit = defineEmits(["update-field"]);
</script>
