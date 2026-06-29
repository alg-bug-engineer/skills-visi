/// <reference types="vite/client" />

// 高德 JS API 全局对象（松类型，避免引入完整高德类型包）
declare global {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const AMap: any
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    AMap: any
    _AMapSecurityConfig?: { securityJsCode?: string }
  }
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const component: DefineComponent<{}, {}, any>
  export default component
}

export {}
