declare global {
  interface Window {
    AMap: typeof AMap
    _AMapSecurityConfig?: { securityJsCode?: string }
  }
}

export type AMapMap = InstanceType<typeof AMap.Map>
export type AMapMarker = InstanceType<typeof AMap.Marker>

const JINAN_CENTER: [number, number] = [117.000923, 36.675807]

let loadPromise: Promise<typeof AMap> | null = null

export function loadAmap(): Promise<typeof AMap> {
  if (typeof window !== 'undefined' && window.AMap) {
    return Promise.resolve(window.AMap)
  }
  if (loadPromise) return loadPromise

  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    return Promise.reject(new Error('未配置 VITE_AMAP_KEY'))
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

export function createDarkMap(container: HTMLElement, AMap: typeof window.AMap): AMapMap {
  return new AMap.Map(container, {
    zoom: 11,
    center: JINAN_CENTER,
    viewMode: '2D',
    mapStyle: 'amap://styles/grey',
    features: ['bg', 'road', 'building'],
    showLabel: true,
    backgroundColor: '#020810',
  })
}

export function flyTo(
  map: AMapMap,
  _AMap: typeof window.AMap,
  center: [number, number],
  zoom: number,
  duration = 1600,
): Promise<void> {
  return new Promise((resolve) => {
    map.setStatus({ animateEnable: true })
    map.setZoomAndCenter(zoom, center, false, duration)
    window.setTimeout(resolve, duration + 80)
  })
}

/** 将地理中心点偏移到屏幕指定像素位置（用于右侧有面板时居中路口） */
export function panToVisualCenter(
  map: AMapMap,
  lngLat: [number, number],
  pixelOffsetX: number,
  pixelOffsetY = 0,
): void {
  const px = map.lngLatToContainer(lngLat)
  const x = typeof px.getX === 'function' ? px.getX() : (px as { x: number }).x
  const y = typeof px.getY === 'function' ? px.getY() : (px as { y: number }).y
  const size = map.getSize()
  const w = typeof size.getWidth === 'function' ? size.getWidth() : (size as { width: number }).width
  const h = typeof size.getHeight === 'function' ? size.getHeight() : (size as { height: number }).height
  const targetX = w / 2 + pixelOffsetX
  const targetY = h / 2 + pixelOffsetY
  map.panBy(targetX - x, targetY - y)
}

export { JINAN_CENTER }
