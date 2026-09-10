<script setup lang="ts">
/**
 * Porta de entrada do editor.
 *
 * Envolve toda tela de edição e só libera o slot quando o SERVIDOR confirmou
 * três coisas: existe sessão, o usuário tem permissão de storefront, e o site
 * do endereço é dele. As três respostas vêm de `/storefront/auth/session/` —
 * nenhuma é decidida aqui. É o que impede que trocar `burger` por
 * `pizzapalace` na barra de endereço abra o editor do vizinho: o 403 do
 * servidor é o que fecha a porta, e ele fecha mesmo que este componente tivesse
 * um bug.
 *
 * `.client.vue` porque a sessão vive em cookie do navegador: no SSR não há
 * cookie de operador para enviar, e renderizar o formulário no servidor só
 * produziria um flash de "entre" para quem já está logado.
 */
const props = defineProps<{ siteSlug: string }>()

const auth = useStorefrontAuth()
const { state, failure, session } = auth

const username = ref('')
const password = ref('')
const submitting = ref(false)

async function submit() {
  if (submitting.value) return
  submitting.value = true
  try {
    await auth.signIn(username.value.trim(), password.value, props.siteSlug)
  } finally {
    submitting.value = false
    password.value = ''
  }
}

onMounted(() => auth.ensureSession(props.siteSlug))
// Trocar de site sem recarregar a página tem de revalidar: a sessão anterior
// pode não ter direito ao site novo.
watch(() => props.siteSlug, (slug) => auth.ensureSession(slug))
</script>

<template>
  <div v-if="state === 'loading'" class="sf-gate">
    <p class="sf-gate__hint">Verificando sua sessão…</p>
  </div>

  <div v-else-if="state === 'forbidden'" class="sf-gate">
    <div class="sf-gate__card">
      <h1>Sem acesso a este site</h1>
      <p class="sf-gate__hint">{{ failure || 'Este site não pertence ao seu restaurante.' }}</p>
      <p v-if="session?.sites?.length" class="sf-gate__hint">
        Você pode editar:
        <a v-for="item in session.sites" :key="item.id" :href="`/${item.slug}/editor/`">{{ item.name || item.slug }}</a>
      </p>
      <button type="button" class="sf-gate__ghost" @click="auth.signOut()">Entrar com outro usuário</button>
    </div>
  </div>

  <div v-else-if="state === 'anonymous'" class="sf-gate">
    <form class="sf-gate__card" @submit.prevent="submit">
      <h1>Editor do site</h1>
      <p class="sf-gate__hint">Entre com o seu usuário do StarChef para editar <strong>{{ siteSlug }}</strong>.</p>

      <label class="sf-gate__field">
        <span>Usuário ou e-mail</span>
        <input v-model="username" type="text" autocomplete="username" required autofocus>
      </label>

      <label class="sf-gate__field">
        <span>Senha</span>
        <input v-model="password" type="password" autocomplete="current-password" required>
      </label>

      <p v-if="failure" class="sf-gate__error">{{ failure }}</p>

      <button type="submit" class="sf-gate__submit" :disabled="submitting">
        {{ submitting ? 'Entrando…' : 'Entrar' }}
      </button>
    </form>
  </div>

  <slot v-else />
</template>

<style>
/* A porta abre ANTES de o builder montar, então o CSS dele precisa chegar por
   aqui também — senão o formulário de entrada apareceria sem estilo nenhum. */
@import '~/assets/css/builder.css';
</style>
