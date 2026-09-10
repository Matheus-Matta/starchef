import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

/**
 * Os testes de unidade rodam sem o Nuxt.
 *
 * O compiler, o sanitizador e o mapa de breakpoints são TypeScript puro — não
 * precisam de DOM nem do runtime do Nuxt para serem exercitados, e rodar sem
 * eles deixa a suíte em menos de um segundo. Só os aliases precisam ser
 * repetidos aqui, porque quem os resolve normalmente é o Nuxt.
 */
export default defineConfig({
  resolve: {
    alias: {
      '~~': fileURLToPath(new URL('./', import.meta.url)),
      '@@': fileURLToPath(new URL('./', import.meta.url)),
      '~': fileURLToPath(new URL('./app', import.meta.url)),
      '@': fileURLToPath(new URL('./app', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
    // Por padrão o vitest devolve string VAZIA para todo import de CSS —
    // inclusive `?raw`. A folha do canvas do editor é montada justamente
    // lendo `blocks.css` como texto, então sem isto o teste que protege essa
    // injeção passaria a testar duas strings vazias.
    css: true,
  },
})
