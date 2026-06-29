import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8100'

  return {
    plugins: [vue()],
    server: {
      port: Number(env.VITE_DEV_PORT) || 5570,
      strictPort: true,
      host: env.VITE_DEV_HOST || '127.0.0.1',
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.spec.ts'],
    },
  }
})
