import { defineConfig } from 'vite';
import uni from '@dcloudio/vite-plugin-uni';

// 说明：
// - 服务器地址优先级：设置页/登录页保存的本地地址 > 构建期 VITE_AICHAT_SERVER > 默认 http://127.0.0.1:8000
//   （见 src/api/client.ts），因此这里默认不需要代理。
// - H5 开发期若希望走同源代理规避 CORS，可放开下面的 server.proxy，
//   并将客户端“服务器地址”指向开发服务器自身 origin 的 /v1 反代目标。
export default defineConfig({
  plugins: [uni()],
  // server: {
  //   proxy: {
  //     '/v1': { target: 'http://127.0.0.1:8000', ws: true, changeOrigin: true },
  //   },
  // },
});
