import type { AccountBrief, Agent, AgentConnector, ConversationDetail, ConversationItem } from './types';

/** Wire DTOs use account_id and flat member records; pages use nested view models. */
export function normalizeAgent(raw: Agent & { account_id?: string; connector?: { status?: string }; connector_online?: boolean }): Agent {
  return { ...raw, agent_id: raw.agent_id ?? raw.account_id ?? '', online: raw.online ?? raw.connector_online ?? ['online', 'ready'].includes(raw.connector?.status ?? '') };
}

export function normalizeConnector(raw: AgentConnector & { status?: string }): AgentConnector {
  return { ...raw, online: raw.online ?? ['online', 'ready'].includes(raw.status ?? '') };
}

export function normalizeConversation(raw: ConversationDetail & { status?: string }): ConversationDetail {
  return { ...raw, closed: raw.closed ?? raw.status === 'closed', members: (raw.members ?? []).map((member) => ({
    ...member, conversation_id: member.conversation_id ?? raw.conversation_id,
    account: member.account ?? (member as unknown as AccountBrief),
  })) };
}

export function normalizeConversationItem(raw: ConversationItem & { unread?: string; status?: string; members?: AccountBrief[] }): ConversationItem {
  return { ...raw, unread_count: raw.unread_count ?? Number(raw.unread ?? 0),
    closed: raw.closed ?? raw.status === 'closed', direct_peer: raw.direct_peer ?? (raw.kind === 'direct' ? raw.members?.[0] : undefined) };
}
