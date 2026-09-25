import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// 기본 빌드(dist/)는 Vercel용, `npm run build:single`은 폰에서 바로 여는 단일 HTML(play/)용
export default defineConfig(({ mode }) => ({
  base: './',
  plugins: [react(), tailwindcss(), ...(mode === 'single' ? [viteSingleFile()] : [])],
  build: mode === 'single' ? { outDir: 'play', emptyOutDir: true } : {},
}))
