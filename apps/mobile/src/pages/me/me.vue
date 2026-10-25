<template>
  <view class="page">
    <!-- 资料卡 -->
    <view class="card profile">
      <view class="avatar big">{{ initial }}</view>
      <view class="profile-body">
        <view class="profile-name">{{ account?.display_name || account?.handle || '未登录' }}</view>
        <view class="list-sub">@{{ account?.handle || '-' }} · {{ account?.kind === 'human' ? '人类账号' : 'AI 账号' }}</view>
        <view v-if="account?.bio" class="profile-bio">{{ account.bio }}</view>
      </view>
    </view>

    <!-- 功能入口 -->
    <view class="card menu">
      <view class="menu-item" @tap="go('/pages/agents/agents')">
        <text>我的 AI</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu-item" @tap="go('/pages/pairing/scan')">
        <text>扫码 / 配对连接器</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu-item" @tap="showServer = !showServer">
        <text>服务器地址</text>
        <text class="menu-value">{{ serverBase }}</text>
      </view>
      <view v-if="showServer" class="server-edit">
        <input v-model="serverBaseInput" class="input" placeholder="http://host:port" />
        <view class="btn btn-primary btn-small" @tap="saveServerBase">保存</view>
      </view>
    </view>

    <view class="card">
      <view class="btn btn-danger" @tap="logout">退出登录</view>
    </view>

    <view class="foot-note">AIChat 移动端 v0.1.0 · 仅前台实时，回前台自动补齐消息</view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import { describeError, getServerBase, setServerBase } from '../../api/client';

const authStore = useAuthStore();

const showServer = ref(false);
const serverBase = ref(getServerBase());
const serverBaseInput = ref(getServerBase());

const account = computed(() => authStore.account);
const initial = computed(() => (account.value?.display_name || account.value?.handle || 'A').slice(0, 1).toUpperCase());

onShow(async () => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/login' });
    return;
  }
  serverBase.value = getServerBase();
  serverBaseInput.value = serverBase.value;
  try {
    await authStore.refreshMe();
  } catch {
    // 资料刷新失败不打扰
  }
});

function go(url: string) {
  uni.navigateTo({ url });
}

function saveServerBase() {
  try {
    const normalized = setServerBase(serverBaseInput.value);
    serverBase.value = normalized;
    uni.showToast({ title: '已保存', icon: 'success' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function logout() {
  uni.showModal({
    title: '退出登录',
    content: '将清除本地登录状态与消息缓存',
    confirmText: '退出',
    success: async (res) => {
      if (!res.confirm) return;
      await authStore.logout();
      uni.reLaunch({ url: '/pages/login/login' });
    },
  });
}
</script>

<style lang="scss" scoped>
.profile {
  display: flex;
  align-items: center;
}
.avatar.big {
  width: 120rpx;
  height: 120rpx;
  border-radius: 24rpx;
  font-size: 44rpx;
}
.profile-body {
  flex: 1;
  min-width: 0;
  margin-left: 24rpx;
}
.profile-name {
  font-size: 34rpx;
  font-weight: 600;
}
.profile-bio {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #8a9099;
}
.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 0;
  border-bottom: 1rpx solid #f0f1f3;
  font-size: 28rpx;
}
.menu-item:last-child {
  border-bottom: none;
}
.menu-value {
  font-size: 24rpx;
  color: #8a9099;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.arrow {
  color: #c2c8d0;
  font-size: 32rpx;
}
.server-edit {
  display: flex;
  gap: 16rpx;
  align-items: center;
  padding-top: 20rpx;
  .input {
    flex: 1;
  }
}
.foot-note {
  text-align: center;
  color: #b6bcc4;
  font-size: 22rpx;
  margin: 40rpx 0;
}
</style>
