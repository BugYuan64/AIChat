/** 联系人（PROTOCOL.md §2） */
import { request } from './client';
import type { AccountBrief, ContactItem } from './types';

/** 按账号名精确查找，返回有限资料；未命中抛 NOT_FOUND */
export function findAccountByHandle(handle: string) {
  return request<AccountBrief>({ url: '/v1/accounts/by-handle', query: { handle } });
}

/** 发送联系人申请；目标是 AI 时由其所有者审批 */
export function sendContactRequest(target_account_id: string) {
  return request<{ request_id: string; status: string }>({
    url: '/v1/contact-requests',
    method: 'POST',
    data: { target_account_id },
  });
}

/** 处理收到的申请（accept / reject） */
export function decideContactRequest(request_id: string, decision: 'accept' | 'reject') {
  return request<unknown>({
    url: `/v1/contact-requests/${encodeURIComponent(request_id)}/decision`,
    method: 'POST',
    data: { decision },
  });
}

/** items: account + 关系（含 pending_incoming/pending_outgoing 用于“待处理申请”） */
export function listContacts() {
  return request<{ items: ContactItem[] }>({ url: '/v1/contacts' });
}

/** 移除联系人（阻止新私聊，历史保留） */
export function removeContact(account_id: string) {
  return request<unknown>({ url: `/v1/contacts/${encodeURIComponent(account_id)}`, method: 'DELETE' });
}

/** 拉黑（方向性） */
export function blockContact(account_id: string) {
  return request<unknown>({ url: `/v1/contacts/${encodeURIComponent(account_id)}/block`, method: 'POST' });
}
