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
      <button class="icon-button login-screen__theme" type="button" aria-label="Tema" @click="toggleTheme">
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>

      <form class="login-screen__form" @submit.prevent="submit">
        <div class="login-screen__heading">
          <h1>Bem-vindo de volta</h1>
          <p>Entre para acessar o painel da sua filial.</p>
        </div>

        <Input v-model="username" label="Usuário ou e-mail" type="text" placeholder="manager ou voce@restaurante.com" required>
          <template #icon><AppIcon name="mail" :size="17" /></template>
        </Input>

        <Input v-model="password" label="Senha" :type="showPassword ? 'text' : 'password'" placeholder="••••••••" required>
          <template #icon><AppIcon name="lock" :size="17" /></template>
          <template #trailing>
            <button class="login-screen__password-toggle" type="button" @click="showPassword = !showPassword">
              <AppIcon :name="showPassword ? 'eye-off' : 'eye'" :size="17" />
            </button>
          </template>
        </Input>

        <div class="login-screen__row">
          <Switch v-model="remember" label="Lembrar-me" size="sm" />
          <a href="#">Esqueci a senha</a>
        </div>

        <p v-if="errorMessage" class="login-screen__error">{{ errorMessage }}</p>

        <Button type="submit" full-width size="lg" :loading="auth.loading" :variant="done ? 'success' : 'primary'">
          <template v-if="done" #icon><AppIcon name="check" :size="18" /></template>
          {{ done ? "Conectado" : "Entrar" }}
        </Button>

        <div class="login-screen__divider">
          <span />
          <small>ou</small>
          <span />
        </div>

        <Button variant="secondary" full-width size="lg">
          <template #icon><AppIcon name="shield-check" :size="18" /></template>
          Entrar com SSO do restaurante
        </Button>

        <p class="login-screen__support">
          Problemas para acessar? <a href="#">Fale com o suporte</a>
        </p>
      </form>
    </section>
  </div>
</template>

<script setup>
import { ref, watchEffect } from "vue";
import { useRoute, useRouter } from "vue-router";

import logoUrl from "../assets/logo-mark.svg";
import AppIcon from "../components/AppIcon.vue";
import Button from "../components/forms/Button.vue";
import Input from "../components/forms/Input.vue";
import Switch from "../components/forms/Switch.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const theme = ref(localStorage.getItem("starchef-theme") || "light");
const username = ref("");
const password = ref("");
const showPassword = ref(false);
const remember = ref(true);
const done = ref(false);
const errorMessage = ref("");
const features = [
  { icon: "receipt-text", label: "Pedidos & comandas" },
  { icon: "soup", label: "KDS ao vivo" },
  { icon: "wallet", label: "Caixa & pagamentos" },
];

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("starchef-theme", theme.value);
});

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

async function submit() {
  errorMessage.value = "";

  try {
    await auth.login({
      username: username.value,
      password: password.value,
    });
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

.login-screen__theme {
  position: absolute;
  top: 24px;
  right: 24px;
  background: var(--surface-card);
}

.login-screen__form {
  width: 100%;
  max-width: 384px;
  display: flex;
  flex-direction: column;
  gap: 22px;
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

.login-screen__password-toggle {
  display: inline-flex;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-subtle);
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
