/**
 * 统一请求封装 —— 所有页面/Store 的 HTTP 调用必须经此模块，不允许散落 uni.request。
 *
 * 职责（对齐 contracts/PROTOCOL.md §0/§1）：
 * 1. baseURL 从本地存储读取（登录页「服务器设置」/「我的」页可修改），支持构建期 VITE_AICHAT_SERVER 预置；
 * 2. 自动附带 Authorization: Bearer <access_token>（audience=human）；
 * 3. 401（AUTH_INVALID / SESSION_REVOKED）时静默调用 POST /v1/auth/refresh 恰好一次（单飞，
 *    刷新凭据轮换），成功后重放原请求；仍失败则清理凭据、广播 AUTH_EXPIRED_EVENT 并跳登录页；
 * 4. 按 {"request_id", "data" | "error"} 信封解包，错误抛出 ApiClientError；
 * 5. 维护「错误码 → 用户可读中文文案」映射 describeError()。
 */
import type { Account, AccountBrief, ApiErrorBody } from './types';
import { normalizeServerOrigin } from '../pages/login/model';

/* ---------------- 本地存储键 ---------------- */

export const STORAGE_KEYS = {
  serverBase: 'aichat.server_base',
  accessToken: 'aichat.access_token',
  refreshToken: 'aichat.refresh_token',
  account: 'aichat.account',
  /** 事件游标（大数十进制字符串），由 stores/chat.ts 持久化 */
  eventCursor: 'aichat.event_cursor',
  /** 未发送草稿（跨冷启动保留；401 强退不清，主动登出才清），见 utils/drafts.ts */
  drafts: 'aichat.drafts',
} as const;

/** client.ts 在刷新失败清理凭据后广播该事件；App.vue 监听并复位本地状态/停止 WSS */
export const AUTH_EXPIRED_EVENT = 'aichat:auth-expired';

const DEFAULT_SERVER_BASE: string = import.meta.env.VITE_AICHAT_SERVER || 'http://127.0.0.1:8000';

/* ---------------- 错误码（§0 错误码表 + 客户端本地码） ---------------- */

export const ErrorCodes = {
  VALIDATION_FAILED: 'VALIDATION_FAILED',
  VERSION_UNSUPPORTED: 'VERSION_UNSUPPORTED',
  AUTH_INVALID: 'AUTH_INVALID',
  SESSION_REVOKED: 'SESSION_REVOKED',
  FORBIDDEN: 'FORBIDDEN',
  MEMBERSHIP_REVOKED: 'MEMBERSHIP_REVOKED',
  NOT_FOUND: 'NOT_FOUND',
  IDEMPOTENCY_CONFLICT: 'IDEMPOTENCY_CONFLICT',
  VERSION_CONFLICT: 'VERSION_CONFLICT',
  CURSOR_EXPIRED: 'CURSOR_EXPIRED',
  CAPABILITY_UNSUPPORTED: 'CAPABILITY_UNSUPPORTED',
  RATE_LIMITED: 'RATE_LIMITED',
  SLOW_DOWN: 'SLOW_DOWN',
  TEMPORARILY_UNAVAILABLE: 'TEMPORARILY_UNAVAILABLE',
  PAIRING_PENDING: 'PAIRING_PENDING',
  PAIRING_DENIED: 'PAIRING_DENIED',
  PAIRING_EXPIRED: 'PAIRING_EXPIRED',
  PAIRING_REVOKED: 'PAIRING_REVOKED',
  PAIRING_CONSUMED: 'PAIRING_CONSUMED',
  CONTEXT_TOO_LARGE: 'CONTEXT_TOO_LARGE',
  STALE_FENCE: 'STALE_FENCE',
  DELTA_GAP: 'DELTA_GAP',
  // ---- 以下为客户端本地错误码（不会由服务端返回）----
  NETWORK_ERROR: 'NETWORK_ERROR',
  MALFORMED_ENVELOPE: 'MALFORMED_ENVELOPE',
  HTTP_ERROR: 'HTTP_ERROR',
} as const;

export type ErrorCode = (typeof ErrorCodes)[keyof typeof ErrorCodes];

/** 错误码 → 用户提示文案 */
const ERROR_MESSAGES: Record<string, string> = {
  [ErrorCodes.VALIDATION_FAILED]: '请求内容不合法，请检查后重试',
  [ErrorCodes.VERSION_UNSUPPORTED]: '协议版本不兼容，请升级客户端',
  [ErrorCodes.AUTH_INVALID]: '登录已过期，请重新登录',
  [ErrorCodes.SESSION_REVOKED]: '登录状态已撤销，请重新登录',
  [ErrorCodes.FORBIDDEN]: '没有权限执行此操作',
  [ErrorCodes.MEMBERSHIP_REVOKED]: '你的成员身份已失效',
  [ErrorCodes.NOT_FOUND]: '内容不存在或不可见',
  [ErrorCodes.IDEMPOTENCY_CONFLICT]: '请求冲突，请勿重复提交相同内容',
  [ErrorCodes.VERSION_CONFLICT]: '数据已被更新，请刷新后重试',
  [ErrorCodes.CURSOR_EXPIRED]: '同步游标已过期，正在重新同步',
  [ErrorCodes.CAPABILITY_UNSUPPORTED]: '该能力不受支持',
  [ErrorCodes.RATE_LIMITED]: '操作过于频繁，请稍后再试',
  [ErrorCodes.SLOW_DOWN]: '操作过于频繁，请稍后再试',
  [ErrorCodes.TEMPORARILY_UNAVAILABLE]: '服务暂时不可用，请稍后重试',
  [ErrorCodes.PAIRING_PENDING]: '配对仍在等待确认',
  [ErrorCodes.PAIRING_DENIED]: '配对已被拒绝',
  [ErrorCodes.PAIRING_EXPIRED]: '配对码已过期，请在连接器上重新发起',
  [ErrorCodes.PAIRING_REVOKED]: '配对已被撤销',
  [ErrorCodes.PAIRING_CONSUMED]: '配对码已被使用',
  [ErrorCodes.CONTEXT_TOO_LARGE]: '上下文内容过长，无法处理',
  [ErrorCodes.STALE_FENCE]: '任务状态已过期，请刷新',
  [ErrorCodes.DELTA_GAP]: '流式输出出现缺片，已请求检查点修复',
  [ErrorCodes.NETWORK_ERROR]: '网络异常，请检查网络或服务器地址',
  [ErrorCodes.MALFORMED_ENVELOPE]: '服务响应格式异常',
  [ErrorCodes.HTTP_ERROR]: '请求失败，请稍后重试',
};

/** 任意异常 → 中文提示（页面 toast 统一使用）
 *  AUTH_INVALID 双义:登录/刷新接口返回时是"凭据错误",其他接口返回时是"会话失效"。
 *  凭登录页上下文区分文案,避免密码错误被误报成"登录已过期"。 */
export function describeError(e: unknown): string {
  if (e instanceof ApiClientError) {
    if (e.code === ErrorCodes.AUTH_INVALID) {
      return isLoginContext()
        ? '账号名或密码错误'
        : ERROR_MESSAGES[ErrorCodes.AUTH_INVALID];
    }
    return ERROR_MESSAGES[e.code] ?? (e.message || '请求失败');
  }
  if (e instanceof Error && e.message) return e.message;
  return '请求失败';
}

/** 当前页面是否为登录页(登录/注册表单的错误都按"凭据错误"表述) */
function isLoginContext(): boolean {
  const pages = getCurrentPages();
  const route = pages[pages.length - 1]?.route ?? '';
  return route.includes('login');
}

/* ---------------- ApiClientError ---------------- */

export class ApiClientError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly retryAfterMs?: number;
  readonly status: number;

  constructor(body: Partial<ApiErrorBody> & { code: string }, status = 0) {
    super(body.message || body.code);
    this.name = 'ApiClientError';
    this.code = body.code;
    this.retryable = !!body.retryable;
    this.retryAfterMs = body.retry_after_ms;
    this.status = status;
  }
}

/* ---------------- 服务器地址 ---------------- */

/** 读取服务器地址（去掉尾部斜杠） */
export function getServerBase(): string {
  const v: unknown = uni.getStorageSync(STORAGE_KEYS.serverBase);
  if (typeof v === 'string' && v.trim() !== '') {
    return v.trim().replace(/\/+$/, '');
  }
  return DEFAULT_SERVER_BASE.replace(/\/+$/, '');
}

/**
 * 保存服务器地址；非法时抛出 Error（调用方 toast）。
 * 仅接受完整 origin（http:// 或 https://），WSS 地址由其推导（http→ws / https→wss）。
 */
export function setServerBase(url: string): string {
  const normalized = normalizeServerOrigin(url);
  uni.setStorageSync(STORAGE_KEYS.serverBase, normalized);
  return normalized;
}

/* ---------------- 凭据读写（存储为唯一事实来源，避免 Store 循环依赖） ---------------- */

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export function readTokens(): TokenPair | null {
  const a: unknown = uni.getStorageSync(STORAGE_KEYS.accessToken);
  const r: unknown = uni.getStorageSync(STORAGE_KEYS.refreshToken);
  if (typeof a === 'string' && a) {
    return { access_token: a, refresh_token: typeof r === 'string' ? r : '' };
  }
  return null;
}

export function writeTokens(t: TokenPair): void {
  uni.setStorageSync(STORAGE_KEYS.accessToken, t.access_token);
  if (t.refresh_token) uni.setStorageSync(STORAGE_KEYS.refreshToken, t.refresh_token);
}

export function readAccount(): Account | null {
  const raw: unknown = uni.getStorageSync(STORAGE_KEYS.account);
  if (!raw) return null;
  try {
    return typeof raw === 'string' ? (JSON.parse(raw) as Account) : (raw as Account);
  } catch {
    return null;
  }
}

export function writeAccount(account: Account | AccountBrief): void {
  uni.setStorageSync(STORAGE_KEYS.account, JSON.stringify(account));
}

/** 清空凭据与账号（不清事件游标；游标归零在登出时由 chat store 处理） */
export function clearAuthStorage(): void {
  uni.removeStorageSync(STORAGE_KEYS.accessToken);
  uni.removeStorageSync(STORAGE_KEYS.refreshToken);
  uni.removeStorageSync(STORAGE_KEYS.account);
}

/* ---------------- 请求核心 ---------------- */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RequestOptions {
  /** 以 /v1 开头的路径 */
  url: string;
  method?: HttpMethod;
  /** 请求体（POST/PUT/PATCH/DELETE）；接口对象类型即可，无需索引签名 */
  data?: object;
  /** 查询参数（undefined/空串跳过） */
  query?: Record<string, string | number | undefined>;
  /** 是否携带 Bearer；默认 true（登录/注册/刷新自身为 false） */
  auth?: boolean;
  timeoutMs?: number;
}

function buildUrl(path: string, query?: Record<string, string | number | undefined>): string {
  let url = path;
  if (query) {
    const qs = Object.entries(query)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join('&');
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }
  return url;
}

/** 只发请求 + 解信封，不做 401 处理 */
function rawRequest<T>(opts: RequestOptions): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const header: Record<string, string> = { 'Content-Type': 'application/json' };
    const tokens = readTokens();
    if (opts.auth !== false && tokens?.access_token) {
      header.Authorization = `Bearer ${tokens.access_token}`;
    }
    uni.request({
      url: getServerBase() + buildUrl(opts.url, opts.query),
      // @dcloudio/types 的 method 联合未列出 PATCH（类型滞后）：H5/App 运行时均支持，小程序阶段复测
      method: (opts.method ?? 'GET') as 'GET',
      data: opts.data,
      header,
      timeout: opts.timeoutMs ?? 15000,
      success: (res) => {
        const body = res.data as { request_id?: string; data?: T; error?: ApiErrorBody } | undefined;
        const ok = res.statusCode >= 200 && res.statusCode < 300;
        if (ok) {
          if (body && typeof body === 'object' && 'request_id' in body) {
            if (body.error) {
              reject(new ApiClientError(body.error, res.statusCode));
            } else {
              resolve(body.data as T);
            }
          } else {
            reject(new ApiClientError({ code: ErrorCodes.MALFORMED_ENVELOPE, message: '服务响应缺少标准信封', retryable: false }, res.statusCode));
          }
        } else {
          reject(
            new ApiClientError(
              body?.error ?? {
                code: ErrorCodes.HTTP_ERROR,
                message: `请求失败（HTTP ${res.statusCode}）`,
                retryable: res.statusCode >= 500,
              },
              res.statusCode,
            ),
          );
        }
      },
      fail: () => {
        reject(new ApiClientError({ code: ErrorCodes.NETWORK_ERROR, message: '网络请求失败', retryable: true }, 0));
      },
    });
  });
}

/* ---------------- 401 静默刷新（单飞） ---------------- */

let refreshPromise: Promise<boolean> | null = null;

function isAuthError(e: unknown): boolean {
  return e instanceof ApiClientError && (e.code === ErrorCodes.AUTH_INVALID || e.code === ErrorCodes.SESSION_REVOKED || (e.status === 401 && e.code !== ErrorCodes.IDEMPOTENCY_CONFLICT));
}

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const tokens = readTokens();
      if (!tokens?.refresh_token) return false;
      try {
        // 刷新凭据轮换：旧 refresh_token 失效，新对整体落盘（PROTOCOL.md §1）
        const data = await rawRequest<{ access_token: string; refresh_token: string }>({
          url: '/v1/auth/refresh',
          method: 'POST',
          data: { refresh_token: tokens.refresh_token },
          auth: false,
        });
        writeTokens(data);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function forceLogout(): void {
  clearAuthStorage();
  uni.$emit(AUTH_EXPIRED_EVENT);
  uni.reLaunch({ url: '/pages/login/login' });
}

/** 对外统一请求入口：解信封 + 401 刷新一次重放 */
export async function request<T>(opts: RequestOptions): Promise<T> {
  try {
    return await rawRequest<T>(opts);
  } catch (e) {
    if (isAuthError(e) && opts.auth !== false && readTokens()?.refresh_token) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return rawRequest<T>(opts);
      }
      forceLogout();
    }
    throw e;
  }
}
