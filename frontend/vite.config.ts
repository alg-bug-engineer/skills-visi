import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// 前后端分离：dev/preview 代理 /api 到后端，免 CORS。
// ECS 公网：export PUBLIC_HOST=8.149.232.39 ECS_PUBLIC_ACCESS=1
const publicHost = process.env.PUBLIC_HOST || process.env.VITE_DEV_PUBLIC_HOST || ''
const port = Number(process.env.FRONTEND_PORT || 5173)
const backendTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

const apiProxy = {
  '/api': {
    target: backendTarget,
    changeOrigin: true,
  },
}

const publicAccessOptions = publicHost
  ? {
      // 浏览器用公网 IP 打开时，资源与 HMR 都指向公网，避免仍回落 localhost
      origin: `http://${publicHost}:${port}`,
      allowedHosts: [publicHost, 'localhost', '127.0.0.1'],
      hmr: {
        host: publicHost,
        port,
        clientPort: port,
      },
    }
  : {
      allowedHosts: true as const,
    }

// 前后端分离：dev 代理 /api 到后端 :8000，免 CORS。
// 生产 `npm run build` 出独立静态 SPA，可交 nginx/任意静态服务托管。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    ...publicAccessOptions,
    proxy: apiProxy,
  },
  preview: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    ...publicAccessOptions,
    proxy: apiProxy,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.{test,spec}.ts'],
    setupFiles: ['tests/setup.ts'],
  },
})
