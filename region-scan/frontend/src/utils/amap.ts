/* eslint-disable @typescript-eslint/no-explicit-any */
export const JINAN_CENTER: [number, number] = [117.000923, 36.675807]

let loadPromise: Promise<any> | null = null

export function loadAmap(): Promise<any> {
  if (typeof window !== 'undefined' && window.AMap) {
    return Promise.resolve(window.AMap)
  }
  if (loadPromise) return loadPromise

  const key = import.meta.env.VITE_AMAP_KEY
  const security = import.meta.env.VITE_AMAP_SECURITY
  if (!key) return Promise.reject(new Error('未配置 VITE_AMAP_KEY'))

  if (security) {
    window._AMapSecurityConfig = { securityJsCode: security }
  }

  loadPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}`
    script.async = true
    script.onload = () => {
      if (window.AMap) resolve(window.AMap)
      else reject(new Error('高德地图加载失败'))
    }
    script.onerror = () => reject(new Error('高德地图脚本加载失败'))
    document.head.appendChild(script)
  })
  return loadPromise
}

export function createMap(container: HTMLElement, AMap: any): any {
  return new AMap.Map(container, {
    zoom: 11,
    center: JINAN_CENTER,
    viewMode: '2D',
    mapStyle: 'amap://styles/grey',
    showLabel: true,
    backgroundColor: '#020810',
  })
}
