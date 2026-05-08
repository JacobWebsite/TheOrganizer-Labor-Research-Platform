import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        // Canonical port :8001 per CLAUDE.md / start-api.bat / api/main.py.
        // 2026-04-27/28: zombie-socket sessions temporarily used :8005 then
        // :8002 to verify fixes mid-session; those workarounds were not
        // committed. If you hit zombie-socket issues on Windows after
        // restarting uvicorn, reboot to free the port rather than shuffling.
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './__tests__/setup.js',
    css: true,
  },
})
