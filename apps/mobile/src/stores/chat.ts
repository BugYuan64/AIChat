/**
 * 聊天 Store：会话列表、按会话缓存的消息、运行状态、事件游标（持久化）。
 *
 * 一致性规则（PROTOCOL.md §4/§5）：
 * - 消息渲染以「HTTP 快照 + revision 合并」为准：message.updated 仅在 revision 更大时覆盖；
 * - 事件按 event_id 去重、cursor 单调推进（applyEventFrame 统一裁决，WSS 与 HTTP 补拉共用）；
 * - cursor 为大数十进制字符串，单调只前进，持久化到本地存储；
 * - AI 消息 status 流转 draft → partial → final；run.delta 追加到内存流式缓冲（不持久化），
 *   终态 message.updated(final) 清除缓冲，由服务端权威文本接管。
 */
import { defineStore } from 'pinia';
import * as chatApi from '../api/chat';
import { STORAGE_KEYS, readAccount } from '../api/client';
import { cmpDecimalString, truncate } from '../utils/misc';
import {
  readDraft,
  readDrafts,
  writeDraft,
  type ConversationDraft,
  type DraftMention,
  type DraftReplySnapshot,
} from '../utils/drafts';
import type {
  AccountBrief,
  ConversationItem,
  EventItem,
  Message,
  Run,
} from '../api/types';

/** 本地待发消息：失败重试沿用同一 client_message_id（幂等键 §4） */
export interface PendingMessage {
  client_message_id: string;
  conversation_id: string;
  text: string;
  mentions: string[];
  reply_to_message_id?: string;
  state: 'sending' | 'failed';
}

/** 聊天页渲染项：服务端消息或本地待发消息 */
export interface DisplayItem {
  key: string;
  message?: Message;
  pending?: PendingMessage;
}

/**
 * 组件对草稿的增量更新：
 * - mentions 可传 account_id 列表（顺带用缓存补名字）或已有快照；
 * - reply 可传整条消息（长按「引用回复」）或快照。
 * 统一在这里归一成可序列化快照，避免组件各自处理。
 */
export interface ComposerDraftPatch {
  text?: string;
  mentions?: Array<string | DraftMention>;
  reply?: Message | DraftReplySnapshot | null;
}

const EMPTY_DRAFT: ConversationDraft = { text: '', mentions: [], reply: null, updated_at: 0 };

/** 引用落成快照：消息对象在冷启动后不存在，必须连发送者名和摘要一起存 */
function toReplySnapshot(
  input: Message | DraftReplySnapshot | null,
  nameOf: (accountId: string) => string,
): DraftReplySnapshot | null {
  if (!input) return null;
  if ('sender_account_id' in input) {
    return {
      message_id: input.message_id,
      sender_name: nameOf(input.sender_account_id),
      text: truncate(input.text ?? '', 60),
    };
  }
  const s = input as DraftReplySnapshot;
  return { message_id: s.message_id, sender_name: s.sender_name || '', text: s.text || '' };
}

/** @提及落成快照：优先用当前成员缓存的名字，回落到此前的快照名（成员未加载时不清空已有名字） */
function toMentionSnapshots(
  input: Array<string | DraftMention>,
  prev: DraftMention[],
  nameOf: (accountId: string) => string,
): DraftMention[] {
  const out: DraftMention[] = [];
  for (const item of input) {
    const id = typeof item === 'string' ? item : item.account_id;
    if (!id) continue;
    const known = typeof item === 'string' ? '' : item.name;
    const name = nameOf(id) || known || prev.find((p) => p.account_id === id)?.name || '';
    out.push({ account_id: id, name });
  }
  return out;
}

interface ConvBrief {
  title: string;
  kind: 'direct' | 'group';
  closed: boolean;
}

const EVENT_ID_DEDUP_CAP = 1000;

export const useChatStore = defineStore('chat', {
  state: () => ({
    /** 会话列表（HTTP 快照 + 事件增量维护） */
    conversations: [] as ConversationItem[],
    convDetails: {} as Record<string, ConvBrief>,
    /** conversation_id → 按 seq 升序的消息数组 */
    messages: {} as Record<string, Message[]>,
    hasMore: {} as Record<string, boolean>,
    snapshotLoaded: {} as Record<string, boolean>,
    loadingEarlier: false,
    /** conversation_id → 本地待发（sending/failed） */
    pending: {} as Record<string, PendingMessage[]>,
    /** 未发送草稿：按会话隔离，写穿到本地存储（401 强退保留，仅主动登出清除）。 */
    composerDrafts: readDrafts() as Record<string, ConversationDraft>,
    /** run_id → Run（run.updated / 发送响应 / 重试响应维护） */
    runs: {} as Record<string, Run>,
    /** conversation_id → account_id → 成员资料（群设置 / @ 选择 / 名称显示） */
    members: {} as Record<string, Record<string, AccountBrief>>,
    myRole: {} as Record<string, string>,
    /** 全局账号资料缓存（联系人/成员填充） */
    accountCache: {} as Record<string, AccountBrief>,
    /** message_id → run.delta 累积的流式文本（仅内存） */
    streamText: {} as Record<string, string>,
    /** message_id → 已收到的最大 chunk_index（重复 delta 幂等跳过） */
    lastChunkIndex: {} as Record<string, number>,
    typing: {} as Record<string, { account_id: string; at: number }[]>,
    presence: {} as Record<string, boolean>,
    activeConversationId: null as string | null,
    /** 事件游标（大数十进制字符串，持久化，单调） */
    cursor: ((uni.getStorageSync(STORAGE_KEYS.eventCursor) as string) || ''),
    seenEventIds: new Set<string>(),
    eventIdQueue: [] as string[],
    /** binding.changed 置位，AI 页面 onShow 时重拉 */
    agentsStale: false,
    /** 会话页「+」选择建群后，跳到联系人页自动进入多选模式 */
    requestGroupCreate: false,
  }),

  getters: {
    sortedConversations(state): ConversationItem[] {
      return [...state.conversations].sort((a, b) => {
        const sa = a.last_message?.seq ?? '';
        const sb = b.last_message?.seq ?? '';
        if (sa && sb) return cmpDecimalString(sb, sa);
        return (b.updated_at ?? '').localeCompare(a.updated_at ?? '');
      });
    },

    totalUnread(state): number {
      return state.conversations.reduce((n, c) => n + (c.unread_count ?? 0), 0);
    },

    /** 聊天页渲染列表：服务端消息（按 seq 升序）+ 本地待发追加在尾部 */
    displayListOf(state) {
      return (cid: string): DisplayItem[] => {
        const msgs = (state.messages[cid] ?? []).map((m) => ({ key: m.message_id, message: m }));
        const pend = (state.pending[cid] ?? []).map((p) => ({ key: `local:${p.client_message_id}`, pending: p }));
        return [...msgs, ...pend];
      };
    },

    /** 消息最终展示文本：final 用权威文本；draft/partial 取 max(检查点文本, 流式缓冲) */
    renderedTextOf(state) {
      return (messageId: string): string => {
        for (const cid of Object.keys(state.messages)) {
          const m = state.messages[cid].find((x) => x.message_id === messageId);
          if (!m) continue;
          if (m.status === 'final') return m.text;
          const buf = state.streamText[messageId] ?? '';
          return buf.length > m.text.length ? buf : m.text;
        }
        return '';
      };
    },

    memberListOf(state) {
      return (cid: string): AccountBrief[] => Object.values(state.members[cid] ?? {});
    },

    displayNameOf(state) {
      return (accountId: string): string => {
        const c = state.accountCache[accountId];
        return c ? (c.display_name || c.handle) : '';
      };
    },

    memberName(state) {
      return (cid: string, accountId: string): string => {
        const m = state.members[cid]?.[accountId];
        if (m) return m.display_name || m.handle;
        return this.displayNameOf(accountId);
      };
    },

    runOf(state) {
      return (runId?: string): Run | undefined => (runId ? state.runs[runId] : undefined);
    },

    /** typing 指示（4 秒窗口），页面配合定时 tick 触发重算 */
    typingOf(state) {
      return (cid: string): string[] => {
        const now = Date.now();
        return (state.typing[cid] ?? [])
          .filter((t) => now - t.at < 4000)
          .map((t) => this.memberName(cid, t.account_id) || '对方');
      };
    },
  },

  actions: {
    /* ---------------- 基础缓存 ---------------- */

    cacheAccounts(accounts: Array<AccountBrief | null | undefined>) {
      for (const a of accounts) {
        if (a && a.account_id) this.accountCache[a.account_id] = a;
      }
    },

    /* ---------------- 游标（单调、持久化） ---------------- */

    setCursor(cursor: string) {
      if (!cursor) return;
      if (this.cursor && cmpDecimalString(cursor, this.cursor) <= 0) return;
      this.cursor = cursor;
      uni.setStorageSync(STORAGE_KEYS.eventCursor, cursor);
    },

    resetCursor() {
      this.cursor = '';
      uni.removeStorageSync(STORAGE_KEYS.eventCursor);
    },

    /* ---------------- 会话与消息快照 ---------------- */

    async loadConversations(isCurrent: () => boolean = () => true) {
      const res = await chatApi.listConversations();
      if (!isCurrent()) return;
      this.conversations = res.items ?? [];
      this.cacheAccounts(this.conversations.map((c) => c.direct_peer));
    },

    async loadConversationDetail(cid: string, isCurrent: () => boolean = () => true) {
      const detail = await chatApi.getConversation(cid);
      if (!isCurrent()) return;
      const map: Record<string, AccountBrief> = {};
      for (const m of detail.members ?? []) map[m.account.account_id] = m.account;
      this.members[cid] = map;
      const me = readAccount()?.account_id;
      this.myRole[cid] = detail.my_role ?? (me ? detail.members?.find?.((m) => m.account?.account_id === me)?.role ?? '' : '');
      this.convDetails[cid] = { title: detail.title ?? '', kind: detail.kind, closed: !!detail.closed };
      this.cacheAccounts((detail.members ?? []).map((m) => m.account));
    },

    /** 进入聊天页：置为活跃会话（抑制未读），确保消息快照与成员资料就绪 */
    async openConversation(cid: string) {
      this.activeConversationId = cid;
      if (!this.snapshotLoaded[cid]) await this.loadInitialMessages(cid);
      if (!this.members[cid]) {
        try {
          await this.loadConversationDetail(cid);
        } catch {
          // 成员资料失败不阻塞消息浏览（@ 选择降级为空）
        }
      }
    },

    closeConversation() {
      this.activeConversationId = null;
    },

    async loadInitialMessages(cid: string, isCurrent: () => boolean = () => true) {
      const page = await chatApi.listMessages(cid, { limit: 30 });
      if (!isCurrent()) return;
      // Merge instead of replacing: a newer event can arrive while HTTP is in flight.
      for (const message of page.items ?? []) this.upsertMessage(message, false);
      this.hasMore[cid] = !!page.has_more;
      this.snapshotLoaded[cid] = true;
    },

    /** 上拉（滚动到顶）加载更早历史；返回值未使用，滚动锚定由页面处理 */
    async loadEarlierMessages(cid: string) {
      const list = this.messages[cid] ?? [];
      if (!list.length || this.loadingEarlier) return;
      this.loadingEarlier = true;
      try {
        const page = await chatApi.listMessages(cid, { before_seq: list[0].seq, limit: 30 });
        const existing = new Set(list.map((m) => m.message_id));
        const fresh = (page.items ?? [])
          .filter((m) => !existing.has(m.message_id))
          .sort((a, b) => cmpDecimalString(a.seq, b.seq));
        this.messages[cid] = [...fresh, ...list];
        this.hasMore[cid] = !!page.has_more;
      } finally {
        this.loadingEarlier = false;
      }
    },

    /* ---------------- 本地待发 ---------------- */

    addPending(p: PendingMessage) {
      (this.pending[p.conversation_id] ??= []).push(p);
    },

    setPendingState(cid: string, clientId: string, state: 'sending' | 'failed') {
      const it = (this.pending[cid] ?? []).find((x) => x.client_message_id === clientId);
      if (it) it.state = state;
    },

    removePending(cid: string, clientId: string) {
      const arr = this.pending[cid] ?? [];
      const i = arr.findIndex((x) => x.client_message_id === clientId);
      if (i >= 0) arr.splice(i, 1);
    },

    /* ---------------- 消息写入（事件 + HTTP 共用） ---------------- */

    /** 新消息插入/覆盖（按 message_id 去重，revision 更大才覆盖），同步维护会话摘要与未读 */
    upsertMessage(m: Message, countUnread = true) {
      if (!m?.message_id || !m.conversation_id) return;
      const cid = m.conversation_id;
      const list = (this.messages[cid] ??= []);
      const idx = list.findIndex((x) => x.message_id === m.message_id);
      let inserted = false;
      if (idx >= 0) {
        if (cmpDecimalString(m.revision, list[idx].revision) > 0) {
          list.splice(idx, 1, m);
        }
      } else {
        let at = 0;
        while (at < list.length && cmpDecimalString(list[at].seq, m.seq) < 0) at++;
        list.splice(at, 0, m);
        inserted = true;
      }
      // 服务端回包/事件确认了本地待发消息（同幂等键、同发送者）
      if (m.client_message_id && m.sender_account_id === readAccount()?.account_id) {
        this.removePending(cid, m.client_message_id);
      }
      this.applyMessageToConversation(m, inserted && countUnread);
    },

    applyMessageToConversation(m: Message, inserted: boolean) {
      const conv = this.conversations.find((c) => c.conversation_id === m.conversation_id);
      if (!conv) return;
      const newer = !conv.last_message?.seq || cmpDecimalString(m.seq, conv.last_message.seq) >= 0;
      if (newer) {
        conv.last_message = {
          seq: m.seq,
          sender_account_id: m.sender_account_id,
          kind: m.kind,
          text: m.text,
          created_at: m.created_at,
        };
        conv.updated_at = m.created_at;
      }
      if (inserted && m.sender_account_id !== readAccount()?.account_id && this.activeConversationId !== m.conversation_id) {
        conv.unread_count = (conv.unread_count ?? 0) + 1;
      }
    },

    /** message.updated：revision 合并；final 时清除流式缓冲 */
    mergeMessage(m: Message) {
      if (!m?.message_id) return;
      const cid = m.conversation_id;
      const list = this.messages[cid];
      if (!list) {
        this.upsertMessage(m);
        return;
      }
      const idx = list.findIndex((x) => x.message_id === m.message_id);
      if (idx < 0) {
        this.upsertMessage(m);
        return;
      }
      if (cmpDecimalString(m.revision, list[idx].revision) > 0) {
        list.splice(idx, 1, m);
        if (m.status === 'final') {
          delete this.streamText[m.message_id];
          delete this.lastChunkIndex[m.message_id];
        }
        const conv = this.conversations.find((c) => c.conversation_id === cid);
        if (conv?.last_message && conv.last_message.seq === m.seq) {
          conv.last_message = { ...conv.last_message, text: m.text, kind: m.kind };
        }
      }
    },

    /* ---------------- 运行状态 ---------------- */

    upsertRun(patch: Partial<Run> & { run_id: string }) {
      if (!patch?.run_id) return;
      this.runs[patch.run_id] = { ...(this.runs[patch.run_id] ?? {}), ...patch } as Run;
    },

    /* ---------------- 临时事件 ---------------- */

    /**
     * run.delta 追加（仅 WSS 临时事件）：
     * 找到该 run 对应的非 final AI 消息；chunk_index 重复则跳过（幂等）；
     * 缺片容忍（显示层面忽略，权威文本以 partial 检查点/final 为准）。
     */
    appendDelta(evt: { run_id: string; message_id?: string; conversation_id?: string; chunk_index?: number; text?: string }) {
      if (!evt?.run_id) return;
      const findByRun = (cid: string): Message | undefined => {
        const arr = this.messages[cid] ?? [];
        for (let i = arr.length - 1; i >= 0; i--) {
          if (arr[i].run_id === evt.run_id && arr[i].status !== 'final') return arr[i];
        }
        return undefined;
      };
      let target: Message | undefined;
      if (evt.message_id) {
        for (const cid of Object.keys(this.messages)) {
          const m = (this.messages[cid] ?? []).find((x) => x.message_id === evt.message_id);
          if (m) {
            target = m;
            break;
          }
        }
      }
      if (!target && evt.conversation_id) target = findByRun(evt.conversation_id);
      if (!target) {
        for (const cid of Object.keys(this.messages)) {
          target = findByRun(cid);
          if (target) break;
        }
      }
      if (!target) return; // draft 消息尚未到达：丢弃，等待 message.created/updated 检查点补全
      const mid = target.message_id;
      if (typeof evt.chunk_index === 'number') {
        const last = this.lastChunkIndex[mid];
        if (typeof last === 'number' && evt.chunk_index <= last) return;
        this.lastChunkIndex[mid] = evt.chunk_index;
      }
      const base = this.streamText[mid] ?? target.text ?? '';
      this.streamText[mid] = base + (evt.text ?? '');
    },

    setTyping(cid: string, accountId: string) {
      const arr = (this.typing[cid] ??= []).filter(
        (t) => t.account_id !== accountId && Date.now() - t.at < 4000,
      );
      arr.push({ account_id: accountId, at: Date.now() });
      this.typing[cid] = arr;
    },

    setPresence(accountId: string, online: boolean) {
      if (accountId) this.presence[accountId] = online;
    },

    /* ---------------- 已读 ---------------- */

    /** 已读上报（through_seq 只前进），本地未读立即清零 */
    async markRead(cid: string, throughSeq: string) {
      const conv = this.conversations.find((c) => c.conversation_id === cid);
      if (conv) conv.unread_count = 0;
      try {
        await chatApi.markRead(cid, throughSeq);
      } catch {
        // 已读只前进：失败静默，下次进入/新消息再上报
      }
    },

    /* ---------------- 事件统一应用（WSS 帧 + HTTP 补拉共用） ---------------- */

    /**
     * 持久事件应用入口：event_id 去重 + cursor 单调，二者任一不满足即丢弃；
     * 通过后按 type 分发，最后推进游标（含持久化）。
     * 返回是否真正应用（用于诊断）。
     */
    applyEventFrame(frame: Pick<EventItem, 'event_id' | 'cursor' | 'type'> & Partial<EventItem>): boolean {
      if (!frame?.event_id || !frame.cursor || !frame.type) return false;
      if (this.seenEventIds.has(frame.event_id)) return false;
      if (this.cursor && cmpDecimalString(frame.cursor, this.cursor) <= 0) return false;

      this.seenEventIds.add(frame.event_id);
      this.eventIdQueue.push(frame.event_id);
      if (this.eventIdQueue.length > EVENT_ID_DEDUP_CAP) {
        const drop = this.eventIdQueue.shift();
        if (drop) this.seenEventIds.delete(drop);
      }

      const payload = (frame.payload ?? {}) as Record<string, unknown>;
      switch (frame.type) {
        case 'message.created':
          if (payload.message_id) this.upsertMessage(payload as unknown as Message);
          break;
        case 'message.updated':
          if (payload.message_id) this.mergeMessage(payload as unknown as Message);
          break;
        case 'membership.changed':
          // 成员变更：失效成员缓存，刷新会话列表（群设置页打开时会重拉详情）
          delete this.members[frame.conversation_id ?? ''];
          void this.loadConversations().catch(() => {});
          break;
        case 'conversation.updated': {
          // 群名等元数据变更：同步列表标题与详情缓存
          const cid = frame.conversation_id;
          const title = payload.title;
          if (cid && typeof title === 'string') {
            const conv = this.conversations.find((c) => c.conversation_id === cid);
            if (conv) conv.title = title;
            if (this.convDetails[cid]) this.convDetails[cid].title = title;
          }
          break;
        }
        case 'conversation.closed':
          if (frame.conversation_id && this.convDetails[frame.conversation_id]) {
            this.convDetails[frame.conversation_id].closed = true;
          }
          void this.loadConversations().catch(() => {});
          break;
        case 'run.updated':
          if (payload.run_id) this.upsertRun(payload as unknown as Partial<Run> & { run_id: string });
          break;
        case 'binding.changed':
          this.agentsStale = true;
          break;
        default:
          // 未知持久事件：跳过内容，仍推进游标（§0：未知可选字段可忽略）
          break;
      }

      this.setCursor(frame.cursor);
      return true;
    },

    /* ---------------- 重同步 ---------------- */

    /** CURSOR_EXPIRED(410) 时的全量 resync：清缓存 → 重拉会话/活跃会话快照；游标由后续事件重新锚定 */
    async fullResync(isCurrent: () => boolean = () => true) {
      const active = this.activeConversationId;
      this.resetAll();
      // resetAll 只清内存：草稿是本地资产，不随服务端 resync 丢失
      this.hydrateDrafts();
      try {
        await this.loadConversations(isCurrent);
      } catch {
        // 网络失败：等待下次 onShow 重试
      }
      if (!isCurrent()) return;
      if (active) {
        this.activeConversationId = active;
        try {
          await this.loadInitialMessages(active, isCurrent);
        } catch {
          /* ignore */
        }
        try {
          if (isCurrent()) await this.loadConversationDetail(active, isCurrent);
        } catch {
          /* ignore */
        }
      }
    },

    /** 更新草稿并写穿本地存储；正文、提及、引用都为空时自动清除该会话的草稿 */
    updateComposerDraft(cid: string, patch: ComposerDraftPatch) {
      if (!cid) return;
      const prev: ConversationDraft = this.composerDrafts[cid] ?? EMPTY_DRAFT;
      const nameOf = (accountId: string) => this.memberName(cid, accountId);
      const next: ConversationDraft = {
        text: patch.text ?? prev.text,
        mentions: patch.mentions ? toMentionSnapshots(patch.mentions, prev.mentions, nameOf) : prev.mentions,
        reply: patch.reply !== undefined ? toReplySnapshot(patch.reply, nameOf) : prev.reply,
        updated_at: Date.now(),
      };
      const blank = !next.text.trim() && !next.mentions.length && !next.reply;
      if (blank) {
        delete this.composerDrafts[cid];
        writeDraft(cid, null);
        return;
      }
      this.composerDrafts[cid] = next;
      writeDraft(cid, next);
    },

    /** 从本地存储重新装载草稿（冷启动 / resync 复位后） */
    hydrateDrafts() {
      this.composerDrafts = readDrafts() as Record<string, ConversationDraft>;
    },

    /** 清空全部本地状态（登出 / resync 复位）；草稿只在内存中清空，存储由 hydrateDrafts 决定 */
    resetAll() {
      this.conversations = [];
      this.convDetails = {};
      this.messages = {};
      this.hasMore = {};
      this.snapshotLoaded = {};
      this.pending = {};
      this.composerDrafts = {};
      this.runs = {};
      this.members = {};
      this.myRole = {};
      this.streamText = {};
      this.lastChunkIndex = {};
      this.typing = {};
      this.presence = {};
      this.activeConversationId = null;
      this.seenEventIds = new Set<string>();
      this.eventIdQueue = [];
      this.agentsStale = false;
      this.requestGroupCreate = false;
      this.loadingEarlier = false;
      this.resetCursor();
    },
  },
});
