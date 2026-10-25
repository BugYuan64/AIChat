/** 认证与账号（PROTOCOL.md §1） */
import { request } from './client';
import type { Account, AuthTokens, RealtimeTicket } from './types';

/** 注册走邀请码 */
export function register(payload: { invite_code: string; handle: string; display_name: string; password: string }) {
  return request<Account>({ url: '/v1/auth/register', method: 'POST', data: payload, auth: false });
}

export function login(payload: { handle: string; password: string; device_summary?: string }) {
  return request<AuthTokens>({ url: '/v1/auth/login', method: 'POST', data: payload, auth: false });
}

/** POST /v1/auth/refresh —— client.ts 内部刷新也走同一路径（此处供 Store 显式调用） */
export function refreshTokens(refresh_token: string) {
  return request<AuthTokens>({ url: '/v1/auth/refresh', method: 'POST', data: { refresh_token }, auth: false });
}

export function logout() {
  return request<{ revoked: boolean }>({ url: '/v1/auth/logout', method: 'POST' });
}

export function fetchMe() {
  return request<Account>({ url: '/v1/me' });
}

/** 换取人类事件 WSS 票据（30 秒一次性，连接后首帧提交） */
export function createRealtimeTicket() {
  return request<RealtimeTicket>({
    url: '/v1/realtime-tickets',
    method: 'POST',
    data: { audience: 'human_events' },
  });
}
