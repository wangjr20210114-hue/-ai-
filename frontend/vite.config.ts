import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { copyFileSync, existsSync, renameSync } from 'node:fs'

function relocateAcceptanceAssets() {
  return {
    name: 'relocate-acceptance-assets',
    closeBundle() {
      const source = resolve(__dirname, 'dist/test-cases')
      const destination = resolve(__dirname, 'dist/acceptance-assets')
      if (existsSync(source) && !existsSync(destination)) renameSync(source, destination)
      const entry = resolve(__dirname, 'dist/test-cases-entry.html')
      if (existsSync(entry)) copyFileSync(entry, resolve(__dirname, 'dist/test-cases'))
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), relocateAcceptanceAssets()],
  build: {
    rollupOptions: {
      input: {
        app: resolve(__dirname, 'index.html'),
        acceptance: resolve(__dirname, 'test-cases-entry.html'),
      },
    },
  },
  server: {
    host: '127.0.0.1',
    allowedHosts: true,
  },
})
