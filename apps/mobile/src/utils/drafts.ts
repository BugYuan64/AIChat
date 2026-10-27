/**
 * 未发送草稿的本地持久化。
 *
 * 契约要求「401 重新认证，保留未发草稿」（docs/消息与HTTP-WSS契约.md § 错误处理），
 * 所以草稿存在独立于登录凭据的存储键里：
 * - clearAuthStorage() 不动它（401 强退后重新登录还能接着写）；
 * - 只有用户主动登出才 clearDrafts()。
 *
 * 草稿除正文外还要记住 @提及 与引用回复：这两者只有在会话消息/成员数据加载完成后
 * 才能由 id 反查名字，若只存 id，冷启动恢复时界面上会出现空白 chip。因此提及存
 * account_id + 名字、引用存 message_id + 发送者名 + 文本摘要，恢复时先用快照渲染，
 * 等真实数据到位后自然覆盖。
 */
import { STORAGE_KEYS } from '../api/client';

/** 引用回复的快照（消息对象可能尚未加载，不能只留 message_id） */
export interface DraftReplySnapshot {
  message_id: string;
  /** 发送者显示名（恢复时直接显示，空白表示当时也未知） */
  sender_name: string;
  /** 原文摘要（已截断，仅用于条带展示） */
  text: string;
}

/** @提及的人（存名字，避免冷启动时成员列表未到导致 chip 空白） */
export interface DraftMention {
  account_id: string;
  name: string;
}

export interface ConversationDraft {
  text: string;
  mentions: DraftMention[];
  reply: DraftReplySnapshot | null;
  /** 最后修改时间（毫秒时间戳），用于排查与过期清理 */
  updated_at: number;
}

/** conversation_id → 草稿 */
export type DraftMap = Record<string, ConversationDraft>;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

function normalizeMention(v: unknown): DraftMention | null {
  if (!isRecord(v)) return null;
  const id = typeof v.account_id === 'string' ? v.account_id : '';
  if (!id) return null;
  return { account_id: id, name: typeof v.name === 'string' ? v.name : '' };
}

function normalizeReply(v: unknown): DraftReplySnapshot | null {
  if (!isRecord(v)) return null;
  const id = typeof v.message_id === 'string' ? v.message_id : '';
  if (!id) return null;
  return {
    message_id: id,
    sender_name: typeof v.sender_name === 'string' ? v.sender_name : '',
    text: typeof v.text === 'string' ? v.text : '',
  };
}

/** 单条草稿校验：字段类型不对就丢弃该项，不让脏数据把整张表读坏 */
function normalizeDraft(v: unknown): ConversationDraft | null {
  if (!isRecord(v)) return null;
  const text = typeof v.text === 'string' ? v.text : '';
  const mentions = Array.isArray(v.mentions)
    ? v.mentions.map(normalizeMention).filter((m): m is DraftMention => !!m)
    : [];
  const reply = normalizeReply(v.reply);
  if (!text.trim() && !mentions.length && !reply) return null;
  return {
    text,
    mentions,
    reply,
    updated_at: typeof v.updated_at === 'number' ? v.updated_at : Date.now(),
  };
}

export function readDrafts(): DraftMap {
  let raw: unknown;
  try {
    raw = uni.getStorageSync(STORAGE_KEYS.drafts);
  } catch {
    return {};
  }
  if (!raw) return {};
  let parsed: unknown = raw;
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return {};
    }
  }
  if (!isRecord(parsed)) return {};
  const out: DraftMap = {};
  for (const [cid, value] of Object.entries(parsed)) {
    const d = normalizeDraft(value);
    if (d) out[cid] = d;
  }
  return out;
}

export function readDraft(conversationId: string): ConversationDraft | null {
  if (!conversationId) return null;
  return readDrafts()[conversationId] ?? null;
}

/** 写入/覆盖一张草稿；内容为空则等同于删除，避免存一堆空记录 */
export function writeDraft(conversationId: string, draft: ConversationDraft | null): void {
  if (!conversationId) return;
  const map = readDrafts();
  const normalized = draft ? normalizeDraft(draft) : null;
  if (normalized) map[conversationId] = normalized;
  else delete map[conversationId];
  try {
    uni.setStorageSync(STORAGE_KEYS.drafts, JSON.stringify(map));
  } catch {
    // 存储满/被禁用时不阻塞输入
  }
}

export function clearDrafts(): void {
  try {
    uni.removeStorageSync(STORAGE_KEYS.drafts);
  } catch {
    // 忽略：下次写入会覆盖
  }
}
