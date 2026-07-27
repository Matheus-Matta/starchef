<template>
  <div class="auth-layout">
    <section class="auth-layout__brand">
      <div class="auth-layout__glow auth-layout__glow--top" />
      <div class="auth-layout__glow auth-layout__glow--bottom" />
      <div class="auth-layout__logo">
        <img src="/logoicon.png" width="46" height="46" alt="StarChef" />
        <span>StarChef</span>
      </div>
      <div class="auth-layout__copy">
        <h2>A cozinha e o salão, no mesmo ritmo.</h2>
        <p>Pedidos, comandas, KDS em tempo real, caixa e relatórios em um só lugar para o seu restaurante.</p>
        <div class="auth-layout__features">
          <div v-for="feature in features" :key="feature.label">
            <span><AppIcon :name="feature.icon" :size="20" /></span>
            <strong>{{ feature.label }}</strong>
          </div>
        </div>
      </div>
      <div class="auth-layout__footer">© 2026 StarChef · MVP de gestão de restaurante</div>
    </section>
    <section class="auth-layout__form-panel">
      <button class="auth-layout__theme-btn" type="button" aria-label="Alternar tema" @click="toggleTheme">
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
      <slot />
    </section>
  </div>
</template>

<script setup>
import { inject } from "vue";
import AppIcon from "../AppIcon.vue";

const theme = inject("theme");
const features = [
  { icon: "receipt-text", label: "Pedidos & comandas" },
  { icon: "soup", label: "KDS ao vivo" },
  { icon: "wallet", label: "Caixa & pagamentos" },
];
function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}
</script>

<style scoped>
.auth-layout { display:grid; grid-template-columns:1.05fr 1fr; min-height:100vh; background:var(--surface-ground); }
.auth-layout__brand { position:relative; overflow:hidden; padding:48px; display:flex; flex-direction:column; justify-content:space-between; background:linear-gradient(150deg,var(--orange-600) 0%,var(--orange-700) 48%,#7c2d12 100%); color:#fff; }
.auth-layout__glow { position:absolute; border-radius:50%; }
.auth-layout__glow--top { top:-120px; right:-80px; width:360px; height:360px; background:radial-gradient(circle,rgba(253,186,116,.45),transparent 70%); }
.auth-layout__glow--bottom { bottom:-140px; left:-100px; width:420px; height:420px; background:radial-gradient(circle,rgba(0,0,0,.25),transparent 70%); }
.auth-layout__logo { position:relative; display:flex; align-items:center; gap:12px; }
.auth-layout__logo img { border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,.25); }
.auth-layout__logo span { font:var(--weight-extra) 24px/1 var(--font-sans); letter-spacing:-.02em; }
.auth-layout__copy { position:relative; display:flex; flex-direction:column; gap:22px; max-width:440px; }
.auth-layout__copy h2 { font:var(--weight-extra) 38px/1.1 var(--font-sans); letter-spacing:-.03em; }
.auth-layout__copy p { font:var(--weight-medium) 15px/1.6 var(--font-sans); color:rgba(255,255,255,.86); }
.auth-layout__features { display:flex; gap:28px; margin-top:6px; }
.auth-layout__features div { display:flex; flex-direction:column; gap:8px; }
.auth-layout__features span { width:40px; height:40px; border-radius:12px; background:rgba(255,255,255,.16); display:inline-flex; align-items:center; justify-content:center; }
.auth-layout__features strong { font:var(--weight-semibold) 12.5px/1.3 var(--font-sans); max-width:92px; }
.auth-layout__footer { position:relative; font:var(--weight-medium) 12.5px/1 var(--font-sans); color:rgba(255,255,255,.7); }
.auth-layout__form-panel { position:relative; display:flex; align-items:center; justify-content:center; padding:40px; }
.auth-layout__theme-btn { position:absolute; top:24px; right:24px; width:38px; height:38px; display:inline-flex; align-items:center; justify-content:center; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--surface-card); color:var(--text-body); cursor:pointer; }
@media (max-width:900px) { .auth-layout { grid-template-columns:1fr; } .auth-layout__brand { min-height:360px; } }
@media (max-width:560px) { .auth-layout__brand,.auth-layout__form-panel { padding:26px; } .auth-layout__features { flex-wrap:wrap; } }
</style>
