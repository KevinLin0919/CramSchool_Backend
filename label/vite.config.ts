import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/label/',
  plugins: [vue()],
  build: { assetsInlineLimit: 0 },
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
})
