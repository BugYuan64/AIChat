<script setup lang="ts">
/**
 * 应用入口：
 * - 启动时从本地存储恢复登录态；未登录重定向到登录页（pages.json 首页即登录页）。
 * - 已登录：前台时启动事件 WSS 客户端；退到后台则停掉（首版只承诺“前台实时 + 恢复前台补齐”，
 *   补齐由 welcome 游标比对触发的 HTTP 补拉完成，见 ws/events.ts）。
 * - client.ts 在 401 刷新失败时通过 uni.$emit(AUTH_EXPIRED_EVENT) 通知这里做清理。
 */
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app';
import { useAuthStore } from './stores/auth';
import { useChatStore } from './stores/chat';
import { startEventsClient, stopEventsClient, catchUp as catchUpEvents } from './ws/events';
import { AUTH_EXPIRED_EVENT } from './api/client';

onLaunch(() => {
  const authStore = useAuthStore();
  authStore.loadFromStorage();

  uni.$on(AUTH_EXPIRED_EVENT, () => {
    stopEventsClient();
    authStore.resetLocal();
    useChatStore().resetAll();
  });
});

onShow(() => {
  const authStore = useAuthStore();
  if (!authStore.isLoggedIn) return;
  // 幂等：已在连接则直接返回；冷启动/回前台时 welcome 阶段会自动判断是否需要 HTTP 补拉
  void catchUpEvents();
  startEventsClient();
});

onHide(() => {
  stopEventsClient();
});
</script>

<style lang="scss">
@import './styles/base.scss';
</style>
