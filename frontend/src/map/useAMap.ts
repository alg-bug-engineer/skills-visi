import { inject, provide, type Ref } from 'vue'
import type { MapController } from './MapController'

const KEY = Symbol('amap-controller')

export function provideAMap(ctrl: Ref<MapController | null>) {
  provide(KEY, ctrl)
}

export function useAMapController(): Ref<MapController | null> {
  const c = inject<Ref<MapController | null>>(KEY)
  if (!c) throw new Error('AMap controller not provided')
  return c
}
