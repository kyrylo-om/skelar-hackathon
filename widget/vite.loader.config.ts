import { defineConfig } from 'vite'

// widget.js: one dependency-free IIFE. It goes into the app's public dir, so the dev server
// serves it at /widget.js and the app build copies it into dist/ next to index.html.
export default defineConfig({
  publicDir: false,
  build: {
    outDir: 'app/public',
    emptyOutDir: false,
    lib: { entry: 'loader/widget.ts', formats: ['iife'], name: 'SupportWidget', fileName: () => 'widget.js' },
  },
})
