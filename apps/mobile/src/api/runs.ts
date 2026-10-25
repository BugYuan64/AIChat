/** 运行（PROTOCOL.md §8） */
import { request } from './client';
import type { Run } from './types';

/** 触发者/所有者/可见成员查看脱敏运行状态 */
export function getRun(run_id: string) {
  return request<Run>({ url: `/v1/runs/${encodeURIComponent(run_id)}` });
}

/** 取消：202 cancel_requested，尽力取消（不承诺外部进程已退出） */
export function cancelRun(run_id: string) {
  return request<Run | { cancel_requested: true } | unknown>({
    url: `/v1/runs/${encodeURIComponent(run_id)}/cancel`,
    method: 'POST',
  });
}

/** 显式重试：新建 Run，指向原运行，旧结果保留 */
export function retryRun(run_id: string) {
  return request<Run>({ url: `/v1/runs/${encodeURIComponent(run_id)}/retry`, method: 'POST' });
}
