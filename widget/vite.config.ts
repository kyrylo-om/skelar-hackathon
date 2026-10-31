import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backendUrl = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'
// The chat app is served from its own origin, so a host page always embeds it cross-origin.
// /api is proxied to Django; in production set VITE_API_BASE (and the backend's CORS) instead.
const server = { host: '127.0.0.1', port: 5174, strictPort: true, proxy: { '/api/': backendUrl } }

export default defineConfig({
  root: 'app', // app/public/widget.js comes from vite.loader.config.ts
  base: './', // assets resolve next to index.html, wherever the widget is hosted
  plugins: [react()],
  build: { outDir: '../dist', emptyOutDir: true },
  server,
  preview: server,
  test: { environment: 'jsdom' },
})
