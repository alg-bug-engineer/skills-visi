import { defineConfig, devices } from '@playwright/test'

// 截图式布局/遮挡自动化测试（对齐 docs/design 为准）。
// dev 服务以 MOCK 数据离线回放，保证可重复。
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1600, height: 900 },
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
    env: { VITE_MOCK: '1' },
  },
})
