// Vitest 全局 setup：jsdom 下补齐 matchMedia（组件读取 reduced-motion）。
if (typeof window !== 'undefined' && !window.matchMedia) {
  // @ts-expect-error 测试桩
  window.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  })
}
