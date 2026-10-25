/**
 * 配对与连接器（PROTOCOL.md §7）——移动端只涉及：
 * 扫码/输码查看配对信息 → 核对 confirm_code → approve/deny；以及撤销连接器。
 * 配对的创建（POST /v1/pairings）与连接器侧轮询/兑换由 connectors/connector-runner 完成。
 */
import { request } from './client';
import type { PairingInfo } from './types';

/** 已登录人类凭 short_code 查看配对详情 */
export function getPairing(pairing_id: string, short_code: string) {
  return request<PairingInfo>({
    url: `/v1/pairings/${encodeURIComponent(pairing_id)}`,
    query: { code: short_code },
  });
}

/**
 * AI 所有者决策：{decision: approve/deny, confirm_code, expected_version}。
 * 说明：规约锁定的请求字段仅以上三个；移动端额外附带可选 agent_id（“选择本人 AI”），
 * 依据 §0「未知可选字段可忽略」，不支持该字段的服务端会忽略它。
 */
export function decidePairing(
  pairing_id: string,
  payload: { decision: 'approve' | 'deny'; confirm_code: string; expected_version: number; agent_id?: string },
) {
  return request<PairingInfo>({
    url: `/v1/pairings/${encodeURIComponent(pairing_id)}/decision`,
    method: 'POST',
    data: payload,
  });
}

/** AI 所有者撤销连接器：关闭其会话，generation+1 */
export function revokeConnector(connector_id: string) {
  return request<unknown>({ url: `/v1/connectors/${encodeURIComponent(connector_id)}/revoke`, method: 'POST' });
}
