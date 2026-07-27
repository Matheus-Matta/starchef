<template>
  <AuthLayout>
    <section class="recovery__form">
      <template v-if="isReset">
        <div class="recovery__heading">
          <h1>Crie uma nova senha</h1>
          <p>Escolha uma senha forte que você não utiliza em outros serviços.</p>
        </div>

        <div v-if="!tokenValid" class="recovery__notice recovery__notice--error">
          Este link está incompleto ou inválido. Solicite uma nova redefinição.
        </div>

        <form v-else-if="!success" @submit.prevent="resetPassword">
          <label for="new-password">Nova senha</label>
          <Password
            v-model="password"
            input-id="new-password"
            toggle-mask
            :feedback="true"
            class="w-full"
            input-class="w-full"
            required
          />

          <label for="confirm-password">Confirme a nova senha</label>
          <Password
            v-model="passwordConfirm"
            input-id="confirm-password"
            toggle-mask
            :feedback="false"
            class="w-full"
            input-class="w-full"
            required
          />

          <p v-if="errorMessage" class="recovery__notice recovery__notice--error">{{ errorMessage }}</p>
          <Button type="submit" label="Redefinir senha" icon="pi pi-lock" :loading="loading" />
        </form>

        <div v-else class="recovery__notice recovery__notice--success">
          Sua senha foi redefinida. Você já pode entrar no StarChef.
        </div>
      </template>

      <template v-else>
        <div class="recovery__heading">
          <h1>Esqueci minha senha</h1>
          <p>Informe seu e-mail. Se ele estiver cadastrado, enviaremos um link seguro.</p>
        </div>

        <form v-if="!success" @submit.prevent="sendLink">
          <label for="recovery-email">E-mail</label>
          <IconField icon-position="left">
            <InputIcon class="pi pi-envelope" />
            <InputText id="recovery-email" v-model.trim="email" type="email" autocomplete="email" required />
          </IconField>
          <p v-if="errorMessage" class="recovery__notice recovery__notice--error">{{ errorMessage }}</p>
          <Button type="submit" label="Enviar link" icon="pi pi-send" :loading="loading" />
        </form>

        <div v-else class="recovery__notice recovery__notice--success">
          Se o e-mail estiver cadastrado, você receberá as instruções em instantes.
        </div>
      </template>

      <RouterLink class="recovery__back" :to="{ name: 'login' }">
        <i class="pi pi-arrow-left" /> Voltar ao login
      </RouterLink>
    </section>
  </AuthLayout>
</template>

<script setup>
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import Button from "primevue/button";
import IconField from "primevue/iconfield";
import InputIcon from "primevue/inputicon";
import InputText from "primevue/inputtext";
import Password from "primevue/password";

import AuthLayout from "../components/auth/AuthLayout.vue";
import { confirmPasswordReset, requestPasswordReset } from "../services/api";

const route = useRoute();
const email = ref("");
const password = ref("");
const passwordConfirm = ref("");
const loading = ref(false);
const success = ref(false);
const errorMessage = ref("");
const isReset = computed(() => route.name === "reset-password");
const token = computed(() => (typeof route.query.token === "string" ? route.query.token : ""));
const tokenValid = computed(() => /^[A-Za-z0-9]{48}$/.test(token.value));

function responseMessage(error, fallback) {
  const message = error.response?.data?.error?.message;
  if (typeof message === "string") return message;
  if (message?.password?.length) return message.password.join(" ");
  if (message?.token?.length) return message.token.join(" ");
  if (message?.password_confirm?.length) return message.password_confirm.join(" ");
  return fallback;
}

async function sendLink() {
  loading.value = true;
  errorMessage.value = "";
  try {
    await requestPasswordReset(email.value);
    success.value = true;
  } catch (error) {
    errorMessage.value = responseMessage(error, "Não foi possível processar a solicitação agora.");
  } finally {
    loading.value = false;
  }
}

async function resetPassword() {
  errorMessage.value = "";
  if (password.value !== passwordConfirm.value) {
    errorMessage.value = "As senhas não coincidem.";
    return;
  }
  loading.value = true;
  try {
    await confirmPasswordReset(token.value, password.value, passwordConfirm.value);
    success.value = true;
    password.value = "";
    passwordConfirm.value = "";
  } catch (error) {
    errorMessage.value = responseMessage(error, "Não foi possível redefinir a senha.");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.recovery__form { width: 100%; max-width: 384px; display: flex; flex-direction: column; gap: 20px; }
.recovery__heading { margin-bottom: 24px; }
.recovery__heading h1 { margin: 0 0 8px; color: var(--text-strong); font: var(--weight-extra) 27px/1.15 var(--font-sans); }
.recovery__heading p { margin: 0; color: var(--text-muted); font: var(--font-body); line-height: 1.55; }
form { display: flex; flex-direction: column; gap: 10px; }
label { margin-top: 5px; color: var(--text-body); font: var(--font-label); }
:deep(.p-inputtext), :deep(.p-password), :deep(.p-button) { width: 100%; }
:deep(.p-inputtext), :deep(.p-button) { min-height: 44px; }
.recovery__notice { padding: 12px 14px; border-radius: var(--radius-md); font: var(--weight-medium) 13px/1.5 var(--font-sans); }
.recovery__notice--success { background: var(--success-subtle); color: var(--success-text); }
.recovery__notice--error { background: var(--danger-subtle); color: var(--danger-text); }
.recovery__back { display: flex; justify-content: center; align-items: center; gap: 8px; margin-top: 24px; color: var(--text-brand); text-decoration: none; font: var(--weight-semibold) 13px/1 var(--font-sans); }
</style>
