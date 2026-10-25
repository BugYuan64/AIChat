/**
 * 认证 Store：token / 账号信息持久化（uni.setStorageSync）。
 * 存储为唯一事实来源（client.ts 直接读写存储），State 只是缓存的投影；
 * 这样 client.ts 的 401 刷新无需反向依赖本 Store，避免循环引用。
 */
import { defineStore } from 'pinia';
import * as authApi from '../api/auth';
import {
  clearAuthStorage,
  readAccount,
  readTokens,
  writeAccount,
  writeTokens,
} from '../api/client';
import { startEventsClient, stopEventsClient } from '../ws/events';
import { useChatStore } from './chat';
import type { Account, AuthTokens } from '../api/types';

function deviceSummary(): string {
  try {
    const info = uni.getSystemInfoSync();
    return `${info.platform || ''} ${info.system || ''} ${info.model || ''}`.trim().slice(0, 120);
  } catch {
    return 'uni-app mobile';
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    account: null as Account | null,
    access_token: '',
    refresh_token: '',
  }),

  getters: {
    isLoggedIn: (s): boolean => !!s.access_token && !!s.account,
    myAccountId: (s): string => s.account?.account_id ?? readAccount()?.account_id ?? '',
  },

  actions: {
    /** App 启动 / 登录页 onShow 时从存储恢复 */
    loadFromStorage() {
      const tokens = readTokens();
      this.access_token = tokens?.access_token ?? '';
      this.refresh_token = tokens?.refresh_token ?? '';
      this.account = readAccount();
    },

    applyAuth(data: AuthTokens) {
      this.access_token = data.access_token;
      this.refresh_token = data.refresh_token;
      this.account = data.account;
      writeTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
      writeAccount(data.account);
    },

    async login(handle: string, password: string) {
      const data = await authApi.login({ handle, password, device_summary: deviceSummary() });
      this.applyAuth(data);
      startEventsClient();
    },

    async register(payload: { invite_code: string; handle: string; display_name: string; password: string }) {
      return authApi.register(payload);
    },

    async refreshMe() {
      this.account = await authApi.fetchMe();
      writeAccount(this.account);
    },

    /** 退出登录：尽力通知服务端撤销会话，随后清理本地状态并停止实时连接 */
    async logout() {
      try {
        await authApi.logout();
      } catch {
        // 服务端撤销失败不阻塞本地登出（token 本地清除即视为登出）
      }
      stopEventsClient();
      this.resetLocal();
      useChatStore().resetAll();
    },

    /** 仅清本地（client.ts 强制登出路径 / 退出登录共用） */
    resetLocal() {
      clearAuthStorage();
      this.access_token = '';
      this.refresh_token = '';
      this.account = null;
    },
  },
});
