import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'
import compression from 'vite-plugin-compression'

// Carrega os .env da RAIZ do monorepo (D:\projetos\starchef\.env), nao da pasta frontend/.
// Assim ha um unico .env para backend e frontend. A Vite so expoe variaveis com prefixo VITE_.
export default defineConfig(({ mode }) => {
  const envDir = fileURLToPath(new URL('..', import.meta.url))
  const env = loadEnv(mode, envDir, '') // '' => carrega TODAS as vars (inclui não-VITE_)

  // Alvo do backend para o proxy do dev server. O app chama a MESMA origem (ex.: /api/v1)
  // e o Vite encaminha para o backend — assim os cookies httpOnly de auth pertencem à
  // origem do frontend, fazendo `hasSession()` e o SameSite=Lax funcionarem inclusive
  // por trás de um devtunnel (onde frontend e backend seriam origens cross-site).
  const backendTarget = env.VITE_BACKEND_TARGET || 'http://localhost:8001'

  const isProd = mode === 'production'

  return {
    plugins: [
      vue(),
      compression({ algorithm: 'gzip', ext: '.gz', threshold: 1024 }),
      compression({ algorithm: 'brotliCompress', ext: '.br', threshold: 1024 }),
    ],
    envDir,
    // Remove console.* e debugger do bundle de produção.
    esbuild: isProd ? { drop: ['console', 'debugger'] } : {},
    server: {
      port: 5173,
      host: '0.0.0.0',
      proxy: {
        '/api': { target: backendTarget, changeOrigin: true },
        // WebSocket das notificações (Channels) no mesmo host.
        '/ws': { target: backendTarget, changeOrigin: true, ws: true },
      },
    },
    build: {
      // Sem sourcemaps em produção (não expõe o código-fonte no navegador).
      sourcemap: !isProd,
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        output: {
          // Separa as libs grandes em chunks próprios (melhor cache do navegador:
          // um deploy de código do app não invalida o vendor). PrimeVue v3 usa
          // imports por subpath, então agrupamos por caminho no node_modules.
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (/[\\/]node_modules[\\/](primevue|primeicons)[\\/]/.test(id)) return 'primevue'
            if (/[\\/]node_modules[\\/](vue|vue-router|pinia|@vue)[\\/]/.test(id)) return 'vue'
            if (/[\\/]node_modules[\\/]axios[\\/]/.test(id)) return 'axios'
          },
        },
      },
    },
  }
})
