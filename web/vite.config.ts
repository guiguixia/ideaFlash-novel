import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __NOVEL_CLIENT_VERSION__: JSON.stringify('0.1.0-openstory'),
  },
  base: (() => {
    const urlPath = (process.env.VITE_URL_PATH || './').trim()
    return urlPath === '/' ? '/' : (urlPath.endsWith('/') ? urlPath : `${urlPath}/`)
  })(),
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@shared': resolve(__dirname, 'shared'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5179,
    strictPort: true,
    proxy: {
      '/rpc': 'http://127.0.0.1:8004',
      '/events': 'http://127.0.0.1:8004',
      '/health': 'http://127.0.0.1:8004',
      '/api': 'http://127.0.0.1:8004',
    },
  },
})
