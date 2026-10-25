/**
 * 会话 / 群 / 消息 / 事件补拉（PROTOCOL.md §3、§4、§5.1）
 */
import { request } from './client';
import type {
  ConversationDetail,
  ConversationItem,
  ConversationRef,
  EventPage,
  Invitation,
  Message,
  MessagePage,
  SendMessagePayload,
  SendMessageResult,
} from './types';

/* ---------------- 会话（§3） ---------------- */

/** 幂等：同一无序账号对已存在则返回原会话（client_request_id 由客户端生成） */
export function createDirectConversation(target_account_id: string, client_request_id: string) {
  return request<ConversationRef>({
    url: '/v1/conversations/direct',
    method: 'POST',
    data: { target_account_id, client_request_id },
  });
}

/** 创建群：创建者为群主，其余成员收到邀请 */
export function createGroup(title: string, member_account_ids: string[]) {
  return request<ConversationRef>({
    url: '/v1/groups',
    method: 'POST',
    data: { title, member_account_ids },
  });
}

/** 群主/管理员邀请；邀请 AI 时被邀方为其所有者（需其确认） */
export function inviteMembers(conversation_id: string, invitee_account_ids: string[]) {
  return request<{ items?: Invitation[] } | unknown>({
    url: `/v1/conversations/${encodeURIComponent(conversation_id)}/invitations`,
    method: 'POST',
    data: { invitee_account_ids },
  });
}

/** 被邀人 / AI 所有者处理邀请 */
export function decideInvitation(invitation_id: string, decision: 'accept' | 'reject') {
  return request<unknown>({
    url: `/v1/invitations/${encodeURIComponent(invitation_id)}/decision`,
    method: 'POST',
    data: { decision },
  });
}

/** 移除成员；对本人 membership 即退群（群主须先转让或解散） */
export function removeMember(conversation_id: string, membership_id: string) {
  return request<unknown>({
    url: `/v1/conversations/${encodeURIComponent(conversation_id)}/members/${encodeURIComponent(membership_id)}`,
    method: 'DELETE',
  });
}

/** 群主解散群 */
export function dissolveConversation(conversation_id: string) {
  return request<unknown>({ url: `/v1/conversations/${encodeURIComponent(conversation_id)}`, method: 'DELETE' });
}

/** 列表 + 最后消息摘要 + 未读 */
export function listConversations() {
  return request<{ items: ConversationItem[] }>({ url: '/v1/conversations' });
}

/** 详情 + 当前成员/角色 */
export function getConversation(conversation_id: string) {
  return request<ConversationDetail>({ url: `/v1/conversations/${encodeURIComponent(conversation_id)}` });
}

/* ---------------- 消息（§4） ---------------- */

/**
 * 发送消息：{client_message_id, text, mentions[]?, reply_to_message_id?}
 * 成功返回 {message, runs[]}；幂等键为 conversation_id + sender + client_message_id，
 * 失败重试必须沿用同一 client_message_id。
 */
export function sendMessage(conversation_id: string, payload: SendMessagePayload) {
  return request<SendMessageResult>({
    url: `/v1/conversations/${encodeURIComponent(conversation_id)}/messages`,
    method: 'POST',
    data: payload,
  });
}

/** 按 seq 升序分页（before_seq 为当前最早一条的 seq），仅返回可见区间 */
export function listMessages(conversation_id: string, opts: { before_seq?: string; limit?: number } = {}) {
  return request<MessagePage>({
    url: `/v1/conversations/${encodeURIComponent(conversation_id)}/messages`,
    query: { before_seq: opts.before_seq, limit: opts.limit },
  });
}

/** 已读上报：through_seq 只前进 */
export function markRead(conversation_id: string, through_seq: string) {
  return request<unknown>({
    url: `/v1/conversations/${encodeURIComponent(conversation_id)}/read`,
    method: 'PUT',
    data: { through_seq },
  });
}

/* ---------------- 事件 HTTP 补拉（§5.1） ---------------- */

/** GET /v1/events?after=<cursor>&limit= ；cursor 过期抛 CURSOR_EXPIRED（410）需全量 resync */
export function fetchEvents(after: string, limit = 200) {
  return request<EventPage>({ url: '/v1/events', query: { after, limit } });
}
