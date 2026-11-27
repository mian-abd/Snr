import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/** Preload the two Latin text fonts, so they download alongside the script instead of after the stylesheet. */
const preloadFonts = (): Plugin => ({
  name: 'preload-fonts',
  transformIndexHtml: {
    order: 'post',
    handler(_html, context) {
      const names = Object.keys(context.bundle ?? {})
      return ['inter-latin-wght-normal', 'source-serif-4-latin-wght-normal']
        .flatMap((stem) => names.filter((name) => name.includes(stem) && name.endsWith('.woff2')))
        .map((name) => ({ tag: 'link', injectTo: 'head' as const, attrs: { rel: 'preload', as: 'font', type: 'font/woff2', crossorigin: '', href: '/' + name } }))
    },
  },
})

export default defineConfig({
  plugins: [react(), preloadFonts()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
