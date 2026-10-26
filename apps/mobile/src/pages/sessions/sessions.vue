<template>
  <view class="page">
    <view v-if="!list.length && !loading" class="empty">
      从一段对话开始
      <view class="empty-sub">通过「联系人」搜索账号发起私聊,或点击右下角 + 创建群聊</view>
    </view>

    <!-- 加载骨架屏(微光) -->
    <view v-if="loading && !list.length" class="card conv-card">
      <view v-for="i in 4" :key="'sk' + i" class="skeleton-row">
        <view class="skeleton skeleton-avatar"></view>
        <view class="skeleton-lines">
          <view class="skeleton skeleton-line l1"></view>
          <view class="skeleton skeleton-line l2"></view>
        </view>
      </view>
    </view>

    <view v-if="list.length" class="card conv-card stagger">
      <view v-for="c in list" :key="c.conversation_id" class="list-item conv-item" @tap="open(c)">
        <view :class="['avatar', c.direct_peer?.kind === 'ai' ? 'ai' : c.kind === 'group' ? 'group' : '']">
          {{ avatarChar(c) }}
        </view>
        <view class="list-body">
          <view class="row-line">
            <text class="list-title">{{ c.title || '会话' }}</text>
            <text v-if="c.direct_peer?.kind === 'ai'" class="tag tag-ai">AI</text>
            <text v-if="c.kind === 'group'" class="tag">群聊</text>
            <text v-if="c.closed" class="tag tag-offline">已解散</text>
          </view>
          <view class="list-sub preview">{{ preview(c) }}</view>
        </view>
        <view class="list-end column-end">
          <text class="time">{{ formatTime(c.last_message?.created_at || c.updated_at) }}</text>
          <view v-if="c.unread_count" class="badge">{{ c.unread_count > 99 ? '99+' : c.unread_count }}</view>
        </view>
      </view>
    </view>

    <view class="fab" aria-label="新建会话" @tap="onCreate"></view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app';
import { useChatStore } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { describeError } from '../../api/client';
import { formatTime, truncate } from '../../utils/misc';
import type { ConversationItem } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const loading = ref(false);
const list = computed(() => chatStore.sortedConversations);

onShow(async () => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/login' });
    return;
  }
  await refresh();
});

onPullDownRefresh(async () => {
  await refresh();
  uni.stopPullDownRefresh();
});

async function refresh() {
  loading.value = true;
  try {
    await chatStore.loadConversations();
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  } finally {
    loading.value = false;
    updateTabBadge();
  }
}

function updateTabBadge() {
  const total = chatStore.totalUnread;
  try {
    if (total > 0) {
      uni.setTabBarBadge({ index: 0, text: total > 99 ? '99+' : String(total) });
    } else {
      uni.removeTabBarBadge({ index: 0 });
    }
  } catch {
    // H5 等平台可能不支持，忽略
  }
}

function avatarChar(c: ConversationItem): string {
  const peer = c.direct_peer;
  const name = peer?.display_name || peer?.handle || c.title || '会';
  return name.slice(0, 1).toUpperCase();
}

function preview(c: ConversationItem): string {
  const lm = c.last_message;
  if (!lm) return '暂无消息';
  const text = lm.kind === 'system' ? lm.text : lm.text.replace(/\s+/g, ' ');
  const name = c.kind === 'group' ? chatStore.displayNameOf(lm.sender_account_id) : '';
  const prefix = name ? `${name}：` : '';
  return truncate(prefix + text, 40);
}

function open(c: ConversationItem) {
  uni.navigateTo({ url: `/pages/chat/chat?id=${c.conversation_id}` });
}

function onCreate() {
  uni.showActionSheet({
    itemList: ['发起私聊（去联系人搜索）', '新建群聊（去联系人选择成员）'],
    success: (res) => {
      chatStore.requestGroupCreate = res.tapIndex === 1;
      uni.switchTab({ url: '/pages/contacts/contacts' });
    },
  });
}
</script>

<style lang="scss" scoped>
.conv-card {
  padding: 8rpx 0;
}
.conv-item {
  border-radius: 20rpx;
  margin: 0 12rpx;
  border-bottom: none;
}
.row-line {
  display: flex;
  align-items: center;
  min-width: 0;
}
.preview {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.column-end {
  flex-direction: column;
  align-items: flex-end;
  gap: 10rpx;
}
.time {
  font-size: 22rpx;
  color: var(--text-faint);
}
.empty-sub {
  font-size: 22rpx;
  margin-top: 12rpx;
  color: var(--text-faint);
}
.fab {
  position: fixed;
  right: 40rpx;
  bottom: 180rpx;
  width: 108rpx;
  height: 108rpx;
  border-radius: 50%;
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10rpx 28rpx rgba(33, 106, 80, 0.35);
  z-index: 10;
  animation: pop-in 0.35s ease-out backwards;
  transition: transform 0.12s ease;
}
.fab:active {
  transform: scale(0.94);
}
/* CSS 绘制的加号,替代文字符号 */
.fab::before,
.fab::after {
  content: '';
  position: absolute;
  background: var(--on-accent);
  border-radius: 3rpx;
}
.fab::before {
  width: 40rpx;
  height: 4rpx;
}
.fab::after {
  width: 4rpx;
  height: 40rpx;
}
/* H5 桌面:列表列居中,FAB 跟随内容列而不是贴屏幕右缘 */
@media (min-width: 768px) {
  .fab {
    right: calc(50% - 360px + 40rpx);
  }
}
</style>
