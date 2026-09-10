<script setup lang="ts">
/**
 * Raiz do servidor, sem site no endereço.
 *
 * Um único processo Nuxt atende todas as lojas, e quem diz qual é o primeiro
 * segmento da URL. Chegar em `/` sem slug não é erro do visitante nem tem uma
 * loja "padrão" para escolher — escolher uma seria mostrar o restaurante errado
 * a quem digitou o endereço pela metade.
 *
 * 404 de propósito: o Google não deve indexar esta tela como se fosse o
 * cardápio de alguém.
 */
definePageMeta({ layout: false })

useHead({ title: 'StarChef · Cardápio digital' })

// Só no SSR: no cliente não existe resposta HTTP para marcar, e `useRequestEvent`
// devolve `undefined` na navegação entre rotas.
const event = useRequestEvent()
if (event) setResponseStatus(event, 404)
</script>

<template>
  <div class="sf-root-empty">
    <div class="sf-root-empty__card">
      <h1>Endereço incompleto</h1>
      <p>
        O cardápio de cada restaurante fica em <code>/nome-do-restaurante/</code>.
        Confira o endereço que você recebeu.
      </p>
    </div>
  </div>
</template>

<style scoped>
.sf-root-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--sf-background);
  font-family: var(--sf-font);
}

.sf-root-empty__card {
  max-width: 420px;
  padding: 28px;
  border: 1px solid var(--sf-border);
  border-radius: var(--sf-radius-lg);
  background: var(--sf-surface);
  text-align: center;
}

.sf-root-empty__card h1 {
  margin: 0 0 10px;
  font-size: 19px;
  color: var(--sf-text);
}

.sf-root-empty__card p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--sf-muted-text);
}
</style>
