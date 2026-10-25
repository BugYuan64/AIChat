/** 通用小工具 */

/**
 * 十进制大数字符串比较（seq / cursor / revision，PROTOCOL.md §0）。
 * 优先 BigInt 精确比较；环境不支持或非法输入时回退 Number/字典序。
 * 返回 -1 / 0 / 1。
 */
export function cmpDecimalString(a: string, b: string): number {
  if (a === b) return 0;
  try {
    const ba = BigInt(a);
    const bb = BigInt(b);
    return ba < bb ? -1 : ba > bb ? 1 : 0;
  } catch {
    const na = Number(a);
    const nb = Number(b);
    if (Number.isFinite(na) && Number.isFinite(nb)) {
      return na < nb ? -1 : na > nb ? 1 : 0;
    }
    return a < b ? -1 : a > b ? 1 : 0;
  }
}

/** 生成本地幂等键（client_message_id / client_request_id），失败重试沿用 */
export function genClientMessageId(): string {
  const rand = Math.random().toString(16).slice(2, 10);
  return `m-${Date.now().toString(36)}-${rand}`;
}

/** 消息时间展示：今天 HH:mm；今年 MM-DD；更早 YYYY-MM-DD */
export function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
