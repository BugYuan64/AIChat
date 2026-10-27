/**
 * 二级页返回导航。
 *
 * 页面栈有上一页时直接回退；直达 URL / 深链进入（如从推送、二维码、浏览器地址栏打开
 * /pages/agents/detail?id=...）时页面栈只有 1 层，原生返回箭头不出现，此时按「所属列表」兜底：
 * - tabBar 页只能走 uni.switchTab（navigateTo/redirectTo 会失败）；
 * - 非 tab 页用 redirectTo 替换当前页，避免在栈里堆出重复的详情页。
 */
export interface BackFallback {
  /** 兜底目标是否为 tabBar 页（sessions / contacts / me） */
  tab?: boolean;
  /** 兜底目标地址（含查询串） */
  url: string;
}

export function goBack(fallback: BackFallback): void {
  if (getCurrentPages().length > 1) {
    uni.navigateBack({});
    return;
  }
  if (fallback.tab) uni.switchTab({ url: fallback.url });
  else uni.redirectTo({ url: fallback.url });
}
