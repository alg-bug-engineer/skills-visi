/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AMAP_KEY: string
  readonly VITE_AMAP_SECURITY: string
  readonly VITE_API_TARGET: string
  readonly VITE_MOCK: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

// 高德安全配置全局注入
interface Window {
  _AMapSecurityConfig?: { securityJsCode: string }
}
