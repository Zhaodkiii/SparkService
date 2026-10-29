import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({plugins:[vue()],server:{host:"0.0.0.0",port:6028,strictPort:true,allowedHosts:["testxhs.dreamwhale.top"],proxy:{'/__oss/':{target:'https://zhaodkdream.oss-cn-beijing.aliyuncs.com',changeOrigin:true,rewrite:p=>p.replace(/^\/__oss/, '')},'/api/public/':{target:'http://127.0.0.1:2026',changeOrigin:true}}}})
