/** AI 与绑定（PROTOCOL.md §6） */
import { request } from './client';
import type { AccountBrief, Agent, AgentConnector } from './types';

/** 创建 AI 账号 + 档案（unbound） */
export function createAgent(payload: { display_name: string; handle: string; bio?: string }) {
  return request<Agent>({ url: '/v1/agents', method: 'POST', data: payload });
}

/** scope=owned：我拥有的 AI；返回档案 + 绑定状态 + 在线状态 */
export function listAgents(scope: 'owned' = 'owned') {
  return request<{ items: Agent[] }>({ url: '/v1/agents', query: { scope } });
}

export function getAgent(agent_id: string) {
  return request<Agent>({ url: `/v1/agents/${encodeURIComponent(agent_id)}` });
}

/** 更新档案：display_name / status */
export function updateAgent(agent_id: string, payload: { display_name?: string; status?: string }) {
  return request<Agent>({ url: `/v1/agents/${encodeURIComponent(agent_id)}`, method: 'PATCH', data: payload });
}

/**
 * 绑定模型 API：credential 为用户录入的密钥，仅此一次提交，服务端加密保存，
 * 连接测试通过后启用。响应为脱敏配置（不含凭据）。
 */
export function bindModel(agent_id: string, payload: { provider_code: string; credential: string; model_name: string; system_prompt?: string }) {
  return request<Agent>({
    url: `/v1/agents/${encodeURIComponent(agent_id)}/model-binding`,
    method: 'POST',
    data: payload,
  });
}

/** 撤销绑定：generation+1，取消在途运行 */
export function revokeBinding(agent_id: string) {
  return request<unknown>({ url: `/v1/agents/${encodeURIComponent(agent_id)}/binding/revoke`, method: 'POST' });
}

/** 授权某人类账号使用该 AI */
export function grantUse(agent_id: string, human_account_id: string) {
  return request<unknown>({
    url: `/v1/agents/${encodeURIComponent(agent_id)}/grants`,
    method: 'POST',
    data: { human_account_id },
  });
}

/** 撤销使用授权 */
export function revokeGrant(agent_id: string, human_account_id: string) {
  return request<unknown>({
    url: `/v1/agents/${encodeURIComponent(agent_id)}/grants`,
    method: 'DELETE',
    data: { human_account_id },
  });
}

/** 所有者查看该 AI 已绑定的连接器 */
export function listConnectors(agent_id: string) {
  return request<{ items: AgentConnector[] } & Record<string, unknown> | AgentConnector[]>({
    url: `/v1/agents/${encodeURIComponent(agent_id)}/connectors`,
  });
}

/** 精确查找人类账号（授权表单用），返回有限资料 */
export function findHumanByHandle(handle: string) {
  return request<AccountBrief>({ url: '/v1/accounts/by-handle', query: { handle } });
}
