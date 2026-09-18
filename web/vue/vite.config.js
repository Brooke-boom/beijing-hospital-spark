import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前后端分离：前端由 Vite 构建为纯静态资源，后端 Flask 只提供 /api/* JSON 接口。
// base 设为 /spa/ —— Flask 会把 dist 挂载在该路径下，与原有单文件大屏（/）并存。
export default defineConfig({
  plugins: [vue()],
  base: '/spa/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // 固定产物文件名，便于 Flask 挂载与版本核对（不做 hash 命名）
    rollupOptions: {
      output: {
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  },
  server: {
    port: 5173,
    // 开发期把 /api 代理到 Flask，避免跨域
    proxy: {
      '/api': { target: 'http://127.0.0.1:5001', changeOrigin: true }
    }
  }
})
