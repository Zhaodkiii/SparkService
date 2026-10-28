import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({plugins:[vue()],server:{host:"0.0.0.0",port:6028,strictPort:true,proxy:{'/api/public/':{target:'http://127.0.0.1:2026',changeOrigin:true}}}})
