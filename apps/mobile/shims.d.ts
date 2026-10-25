/// <reference types="@dcloudio/types" />

// uni-app + Vue3 + TS 的类型占位声明（未安装依赖时也能通过结构检查）

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

declare module '*.json' {
  const value: unknown;
  export default value;
}

// vite/client 已在 tsconfig types 中引入，这里仅补充本项目使用的环境变量
interface ImportMetaEnv {
  /** 构建期默认服务器地址（如 http://192.168.1.10:8000），运行期可被“设置页”覆盖 */
  readonly VITE_AICHAT_SERVER?: string;
}
