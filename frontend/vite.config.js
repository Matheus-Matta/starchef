import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Carrega os .env da RAIZ do monorepo (D:\projetos\starchef\.env), nao da pasta frontend/.
// Assim ha um unico .env para backend e frontend. A Vite so expoe variaveis com prefixo VITE_.
export default defineConfig({
  plugins: [vue()],
  envDir: fileURLToPath(new URL('..', import.meta.url)),
  server: {
    port: 5173,
    host: '0.0.0.0'
  }
})
