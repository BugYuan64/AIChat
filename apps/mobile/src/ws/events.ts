/**
 * 人类事件 WSS 客户端（PROTOCOL.md §5.2，端点 /v1/realtime）。
 *
 * 连接生命周期：
 *   换票据（POST /v1/realtime-tickets, audience=human_events，30s 一次性）
 *   → uni.connectSocket
 *   → 连接后首帧提交 {"type":"ticket","ticket":"..."}（10 秒内，失败即断开）
 *   → 服务端 {"type":"welcome","current_cursor":"..","heartbeat_seconds":20}
 *   → 持久事件帧 / 临时事件帧（run.delta、typing、presence）/ pong。
 *
 * 一致性策略：
 *   1. 持久事件按 event_id 去重、按 cursor 单调应用 —— 两条通路（WSS 帧、HTTP 补拉）
 *      共用 stores/chat.applyEventFrame 统一裁决，乱序/重复安全；
 *   2. welcome 时：本地无游标 → 以 current_cursor 为基线（历史走 HTTP 快照）；
 *      本地游标落后 → 先 GET /v1/events?after=<cursor> 循环补拉闭环缺口；
 *   3. 断线：立即 HTTP 补拉一次（UI 不停滞），随后按指数退避重连（1s 起、上限 60s、带抖动），
 *      welcome 成功后退避复位；票据获取失败同样走退避；
 *   4. 补拉遇到 410 CURSOR_EXPIRED → chat.fullResync() 全量重同步；
 *   5. 心跳：按 welcome.heartbeat_seconds（默认 20s）发送 {"type":"ping"}；
 *      60 秒无任何帧判离线，强制断开重连；
 *   6. run.delta 追加到内存流式缓冲（chunk_index 幂等去重），
 *      终态 message.updated(final) 由 store 清除缓冲。
 *
 * 首版按产品需求只承诺「前台实时，回前台补齐」：App onHide 停止、onShow 重启。
 */
import { createRealtimeTicket } from '../api/auth';
import { fetchEvents } from '../api/chat';
import { ApiClientError, ErrorCodes, getServerBase, readTokens } from '../api/client';
import { useChatStore } from '../stores/chat';
import { cmpDecimalString } from '../utils/misc';
import type { RunDeltaFrame, WelcomeFrame } from '../api/types';

const BASE_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 60000;
const OFFLINE_THRESHOLD_MS = 60000;
const CATCHUP_PAGE_LIMIT = 200;

/** 与 WSS 持久事件帧同构（HTTP items 元素也满足该形状） */
interface PersistentFrame {
  type: string;
  event_id?: string;
  cursor?: string;
  conversation_id?: string;
  seq?: string;
  payload?: unknown;
  occurred_at?: string;
}

let socket: UniApp.SocketTask | null = null;
let wantRunning = false;
let connecting = false;
let backoffMs = BASE_BACKOFF_MS;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let lastFrameAt = 0;
let catchUpPromise: Promise<void> | null = null;

/* ---------------- 对外接口 ---------------- */

/** 幂等启动：未登录忽略；已连接/连接中跳过 */
export function startEventsClient(): void {
  if (!readTokens()?.access_token) return;
  wantRunning = true;
  if (socket || connecting || reconnectTimer) return;
  void connect();
}

/** 停止并断开（退后台 / 登出）；不会触发自动重连 */
export function stopEventsClient(): void {
  wantRunning = false;
  clearTimers();
  if (socket) {
    const s = socket;
    socket = null;
    try {
      s.close({ code: 1000 });
    } catch {
      /* ignore */
    }
  }
}

/** 主动触发一次 HTTP 补拉（App onShow / 断线后调用；与 WSS 帧共用去重与游标裁决） */
export function catchUp(): Promise<void> {
  if (!readTokens()?.access_token) return Promise.resolve();
  if (catchUpPromise) return catchUpPromise;
  catchUpPromise = (async () => {
    const chat = useChatStore();
    let after = chat.cursor;
    if (!after) return; // 无基线游标：等待 WSS welcome 设定基线
    try {
      for (;;) {
        const page = await fetchEvents(after, CATCHUP_PAGE_LIMIT);
        for (const ev of page.items ?? []) {
          chat.applyEventFrame(ev);
        }
        after = page.next_cursor;
        if (!page.has_more) break;
      }
    } catch (e) {
      if (e instanceof ApiClientError && e.code === ErrorCodes.CURSOR_EXPIRED) {
        // 410：事件游标过期（超出保留期）→ 全量 resync
        await chat.fullResync();
      }
      // 其它错误：静默，等待下次 onShow / WSS 重连再补
    } finally {
      catchUpPromise = null;
    }
  })();
  return catchUpPromise;
}

/* ---------------- 内部实现 ---------------- */

function toWsUrl(base: string, path: string): string {
  const wsBase = base.replace(/^http:\/\//i, 'ws://').replace(/^https:\/\//i, 'wss://');
  return `${wsBase}${path}`;
}

async function connect(): Promise<void> {
  if (connecting || socket || !wantRunning) return;
  connecting = true;
  try {
    let ticket: string;
    try {
      const res = await createRealtimeTicket();
      ticket = res.ticket;
    } catch {
      // 票据失败（含 client.ts 自动刷新后仍失败）：退避重试
      scheduleReconnect();
      return;
    }

    const task = uni.connectSocket({
      url: toWsUrl(getServerBase(), '/v1/realtime'),
      success: () => {},
      fail: () => {},
    });
    socket = task;

    task.onOpen(() => {
      lastFrameAt = Date.now();
      // 10 秒内提交一次性票据；发送失败立即断开
      task.send({
        data: JSON.stringify({ type: 'ticket', ticket }),
        fail: () => {
          try {
            task.close({});
          } catch {
            /* ignore */
          }
        },
      });
    });

    task.onMessage((res) => {
      handleFrame(typeof res.data === 'string' ? res.data : String(res.data));
    });

    task.onError(() => {
      // 具体错误信息有限；onClose 随后触发统一走重连
    });

    task.onClose(() => {
      if (socket === task) socket = null;
      clearTimers();
      if (wantRunning) {
        void catchUp(); // 断线立即补拉，避免 UI 停滞
        scheduleReconnect();
      }
    });
  } finally {
    connecting = false;
  }
}

function handleFrame(raw: string): void {
  lastFrameAt = Date.now();
  let frame: Record<string, unknown>;
  try {
    frame = JSON.parse(raw);
  } catch {
    return;
  }
  const type = frame?.type;
  if (typeof type !== 'string') return;

  const chat = useChatStore();
  switch (type) {
    case 'welcome':
      onWelcome(frame as unknown as WelcomeFrame);
      return;
    case 'pong':
    case 'ping':
      return;
    case 'run.delta':
      // 临时事件：流式增量直接进缓冲（chunk 去重在 store 内处理）
      chat.appendDelta(frame as unknown as RunDeltaFrame);
      return;
    case 'typing':
      if (typeof frame.conversation_id === 'string' && typeof frame.account_id === 'string') {
        chat.setTyping(frame.conversation_id, frame.account_id);
      }
      return;
    case 'presence':
      if (typeof frame.account_id === 'string') {
        chat.setPresence(frame.account_id, !!frame.online);
      }
      return;
    default: {
      // 持久事件帧：{"protocol_version":1,"type":"message.created","event_id":"..","cursor":"..",...}
      const pf = frame as unknown as PersistentFrame;
      if (typeof pf.event_id === 'string' && typeof pf.cursor === 'string') {
        chat.applyEventFrame(pf);
      }
    }
  }
}

function onWelcome(frame: WelcomeFrame): void {
  backoffMs = BASE_BACKOFF_MS; // 连接成功，复位退避
  const heartbeatSeconds =
    frame.heartbeat_seconds && frame.heartbeat_seconds > 0 ? frame.heartbeat_seconds : 20;
  startHeartbeat(heartbeatSeconds);

  const chat = useChatStore();
  const current = frame.current_cursor;
  if (!chat.cursor) {
    // 首次运行：以服务端当前游标为基线，历史通过会话/消息 HTTP 快照获得
    chat.setCursor(current);
  } else if (cmpDecimalString(chat.cursor, current) < 0) {
    // 存在缺口：先补拉再消费后续实时事件（补拉与实时帧共用去重/游标裁决）
    void catchUp();
  }
}

function startHeartbeat(seconds: number): void {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (Date.now() - lastFrameAt > OFFLINE_THRESHOLD_MS) {
      // 60 秒无帧：判离线，强制重连
      forceReconnect();
      return;
    }
    try {
      socket?.send({ data: JSON.stringify({ type: 'ping' }) });
    } catch {
      /* ignore */
    }
  }, seconds * 1000);
}

function stopHeartbeat(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function forceReconnect(): void {
  const s = socket;
  socket = null;
  clearTimers();
  try {
    s?.close({});
  } catch {
    /* ignore */
  }
  if (wantRunning) {
    void catchUp();
    scheduleReconnect();
  }
}

function scheduleReconnect(): void {
  if (reconnectTimer || !wantRunning) return;
  const delay = Math.min(backoffMs, MAX_BACKOFF_MS) * (0.8 + Math.random() * 0.4); // 抖动
  backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    void connect();
  }, delay);
}

function clearTimers(): void {
  stopHeartbeat();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}
