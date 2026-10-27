export function canApprovePairing(input: { confirmed: boolean; agentId: string; status?: string; expiresAt?: string; now: number }): boolean {
  const expires = Date.parse(input.expiresAt || '');
  return input.confirmed && !!input.agentId && input.status === 'pending_user' && Number.isFinite(expires) && expires > input.now;
}
export function runPresentation(state: string) {
  const active = ['queued', 'dispatched', 'running'].includes(state);
  const retryable = ['failed', 'cancelled', 'expired', 'recovery_required'].includes(state);
  const tone: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' = state === 'succeeded' ? 'success' : state === 'recovery_required' || state === 'cancel_requested' ? 'warning' : state === 'failed' || state === 'expired' ? 'danger' : active ? 'primary' : 'neutral';
  const labels: Record<string, string> = { queued: '排队中', dispatched: '已派发', running: '运行中', cancel_requested: '正在停止', succeeded: '已完成', failed: '运行失败', cancelled: '已停止', expired: '已超时', recovery_required: '结果未知，需人工处理' };
  return { label: labels[state] || state, active, retryable, tone };
}
