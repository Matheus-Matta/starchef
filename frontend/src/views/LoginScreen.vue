<template>
  <div class="login-screen">
    <section class="login-screen__brand">
      <div class="login-screen__glow login-screen__glow--top" />
      <div class="login-screen__glow login-screen__glow--bottom" />

      <div class="login-screen__logo">
        <img :src="logoUrl" width="46" height="46" alt="StarChef" />
        <span>StarChef</span>
      </div>

      <div class="login-screen__copy">
        <h2>A cozinha e o salão, no mesmo ritmo.</h2>
        <p>Pedidos, comandas, KDS em tempo real, caixa e relatórios em um só lugar para o seu restaurante.</p>
        <div class="login-screen__features">
          <div v-for="feature in features" :key="feature.label">
            <span><AppIcon :name="feature.icon" :size="20" /></span>
            <strong>{{ feature.label }}</strong>
          </div>
        </div>
      </div>

      <div class="login-screen__footer">© 2026 StarChef · MVP de gestão de restaurante</div>
    </section>

    <section class="login-screen__form-panel">
      <button class="login-screen__theme-btn" type="button" aria-label="Tema" @click="toggleTheme">
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>

      <form class="login-screen__form" @submit.prevent="submit">
        <div class="login-screen__heading">
          <h1>Bem-vindo de volta</h1>
          <p>Entre para acessar o painel da sua filial.</p>
        </div>

        <div class="login-field">
          <label for="username" class="login-field__label">Usuário ou e-mail<span>*</span></label>
          <IconField icon-position="left" class="login-field__control">
            <InputIcon class="pi pi-envelope" />
            <InputText
              id="username"
              v-model="username"
              type="text"
              placeholder="manager ou voce@restaurante.com"
              required
              class="w-full"
            />
          </IconField>
        </div>

        <div class="login-field">
          <label for="password" class="login-field__label">Senha<span>*</span></label>
          <Password
            v-model="password"
            input-id="password"
            :feedback="false"
            toggle-mask
            placeholder="••••••••"
            class="w-full"
            input-class="w-full"
          />
        </div>

        <div class="login-screen__row">
          <div class="login-switch">
            <InputSwitch v-model="remember" input-id="remember" />
            <label for="remember">Lembrar-me</label>
          </div>
          <a href="#">Esqueci a senha</a>
        </div>

        <p v-if="errorMessage" class="login-screen__error">{{ errorMessage }}</p>

        <Button
          type="submit"
          :label="done ? 'Conectado' : 'Entrar'"
          :icon="done ? 'pi pi-check' : 'pi pi-sign-in'"
          :loading="auth.loading"
          :severity="done ? 'success' : undefined"
          class="w-full"
          size="large"
        />

        <div class="login-screen__divider">
          <span />
          <small>ou</small>
          <span />
        </div>

        <Button
          label="Entrar com SSO do restaurante"
          icon="pi pi-shield"
          severity="secondary"
          outlined
          class="w-full"
          size="large"
          type="button"
        />

        <p class="login-screen__support">
          Problemas para acessar? <a href="#">Fale com o suporte</a>
        </p>
      </form>
    </section>
  </div>
</template>

<script setup>
import { inject, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import IconField from "primevue/iconfield";
import InputIcon from "primevue/inputicon";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Password from "primevue/password";

import logoUrl from "../assets/logo-mark.svg";
import AppIcon from "../components/AppIcon.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const theme = inject("theme");
const username = ref("");
const password = ref("");
const remember = ref(true);
const done = ref(false);
const errorMessage = ref("");
const features = [
  { icon: "receipt-text", label: "Pedidos & comandas" },
  { icon: "soup", label: "KDS ao vivo" },
  { icon: "wallet", label: "Caixa & pagamentos" },
];

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

async function submit() {
  errorMessage.value = "";
  try {
    await auth.login({ username: username.value, password: password.value });
    done.value = true;
    const next = typeof route.query.next === "string" ? route.query.next : "/painel";
    await router.replace(next);
  } catch (error) {
    const status = error.response?.status;
    if (status === 401) {
      errorMessage.value = "Usuário ou senha inválidos.";
    } else if (status === 403) {
      errorMessage.value = "Conta sem permissão para acessar o sistema.";
    } else {
      errorMessage.value = "Não foi possível entrar agora. Verifique a API e tente novamente.";
    }
  }
}
</script>

<style scoped>
.login-screen {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  min-height: 100vh;
  background: var(--surface-ground);
}

.login-screen__brand {
  position: relative;
  overflow: hidden;
  padding: 48px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: linear-gradient(150deg, var(--orange-600) 0%, var(--orange-700) 48%, #7c2d12 100%);
  color: #fff;
}

.login-screen__glow {
  position: absolute;
  border-radius: 50%;
}

.login-screen__glow--top {
  top: -120px;
  right: -80px;
  width: 360px;
  height: 360px;
  background: radial-gradient(circle, rgba(253, 186, 116, 0.45), transparent 70%);
}

.login-screen__glow--bottom {
  bottom: -140px;
  left: -100px;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(0, 0, 0, 0.25), transparent 70%);
}

.login-screen__logo {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
}

.login-screen__logo img {
  border-radius: 12px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
}

.login-screen__logo span {
  font: var(--weight-extra) 24px/1 var(--font-sans);
  letter-spacing: -0.02em;
}

.login-screen__copy {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 22px;
  max-width: 440px;
}

.login-screen__copy h2 {
  font: var(--weight-extra) 38px/1.1 var(--font-sans);
  letter-spacing: -0.03em;
}

.login-screen__copy p {
  font: var(--weight-medium) 15px/1.6 var(--font-sans);
  color: rgba(255, 255, 255, 0.86);
}

.login-screen__features {
  display: flex;
  gap: 28px;
  margin-top: 6px;
}

.login-screen__features div {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.login-screen__features span {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.16);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.login-screen__features strong {
  font: var(--weight-semibold) 12.5px/1.3 var(--font-sans);
  max-width: 92px;
}

.login-screen__footer {
  position: relative;
  font: var(--weight-medium) 12.5px/1 var(--font-sans);
  color: rgba(255, 255, 255, 0.7);
}

.login-screen__form-panel {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.login-screen__theme-btn {
  position: absolute;
  top: 24px;
  right: 24px;
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  color: var(--text-body);
  cursor: pointer;
}

.login-screen__form {
  width: 100%;
  max-width: 384px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-screen__heading {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.login-screen__heading h1 {
  font: var(--weight-extra) 28px/1.1 var(--font-sans);
  letter-spacing: -0.02em;
  color: var(--text-strong);
}

.login-screen__heading p {
  font: var(--weight-medium) 14px/1.5 var(--font-sans);
  color: var(--text-muted);
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.login-field__label {
  font: var(--font-label);
  color: var(--text-body);
}

.login-field__label span {
  color: var(--danger);
  margin-left: 2px;
}

.login-field__control {
  width: 100%;
  display: flex;
}

.login-switch {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.login-switch label {
  font: var(--font-body);
  color: var(--text-body);
  cursor: pointer;
}

.login-screen__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.login-screen__row a,
.login-screen__support a {
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  color: var(--text-brand);
}

.login-screen__error {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--danger-subtle);
  color: var(--danger-text);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

.login-screen__divider {
  display: flex;
  align-items: center;
  gap: 12px;
}

.login-screen__divider span {
  flex: 1;
  height: 1px;
  background: var(--border);
}

.login-screen__divider small {
  font: var(--weight-medium) 12px/1 var(--font-sans);
  color: var(--text-subtle);
}

.login-screen__support {
  text-align: center;
  font: var(--weight-medium) 13px/1.5 var(--font-sans);
  color: var(--text-muted);
}

:deep(.p-inputtext) {
  width: 100%;
  height: 44px;
  font-family: var(--font-sans);
}

:deep(.p-password) {
  width: 100%;
}

:deep(.p-password .p-inputtext) {
  width: 100%;
  height: 44px;
  font-family: var(--font-sans);
}

:deep(.p-button) {
  height: 44px;
  font-family: var(--font-sans);
  font-weight: var(--weight-semibold);
  justify-content: center;
}

:deep(.p-button.p-button-lg) {
  font-size: var(--text-md);
}

@media (max-width: 900px) {
  .login-screen {
    grid-template-columns: 1fr;
  }

  .login-screen__brand {
    min-height: 360px;
  }
}

@media (max-width: 560px) {
  .login-screen__brand,
  .login-screen__form-panel {
    padding: 26px;
  }

  .login-screen__features {
    flex-wrap: wrap;
  }
}
</style>
