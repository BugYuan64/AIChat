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
      <view class="btn btn-ghost btn-small" @tap="startEditProfile">编辑</view>
    </view>

    <!-- 编辑资料 -->
    <view v-if="editingProfile" class="card">
      <view class="field-label">昵称</view>
      <input v-model="profileForm.display_name" class="input" placeholder="1-128 字符" maxlength="128" />
      <view class="field-label">简介</view>
      <textarea v-model="profileForm.bio" class="textarea" placeholder="一句话介绍（可选）" maxlength="2048" />
      <view class="row-gap">
        <view class="btn btn-primary" @tap="saveProfile">保存</view>
        <view class="btn btn-ghost" @tap="editingProfile = false">取消</view>
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
      <view class="menu-item" @tap="toggleSessions">
        <text>登录设备</text>
        <text class="menu-value">{{ sessions.length ? `${sessions.length} 台在线` : '' }}</text>
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

    <!-- 登录设备列表 -->
    <view v-if="showSessions" class="card">
      <view v-if="sessionsLoading" class="empty">加载中…</view>
      <template v-else>
        <view v-for="s in sessions" :key="s.session_id" class="session-item">
          <view class="list-body">
            <view class="row-line">
              <text class="list-title">{{ s.device_summary || '未知设备' }}</text>
              <text v-if="s.current" class="tag tag-admin">本机</text>
            </view>
            <view class="list-sub">登录于 {{ formatTime(s.created_at) }}</view>
          </view>
          <view v-if="!s.current" class="btn btn-danger btn-small" @tap="revokeSession(s)">下线</view>
        </view>
        <view v-if="!sessions.length" class="empty">暂无活跃会话</view>
        <view class="foot-tip">下线其他设备会使其访问令牌与实时连接立即失效。</view>
      </template>
    </view>

    <view class="card">
      <view class="btn btn-danger" @tap="logout">退出登录</view>
    </view>

    <view class="foot-note">AIChat 移动端 v0.1.0 · 仅前台实时，回前台自动补齐消息</view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import * as authApi from '../../api/auth';
import type { LoginSession } from '../../api/types';
import { describeError, getServerBase, setServerBase } from '../../api/client';

const authStore = useAuthStore();

const showServer = ref(false);
const serverBase = ref(getServerBase());
const serverBaseInput = ref(getServerBase());
const editingProfile = ref(false);
const profileForm = reactive({ display_name: '', bio: '' });

const showSessions = ref(false);
const sessions = ref<LoginSession[]>([]);
const sessionsLoading = ref(false);

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
  if (showSessions.value) await loadSessions();
});

function go(url: string) {
  uni.navigateTo({ url });
}

function startEditProfile() {
  profileForm.display_name = account.value?.display_name ?? '';
  profileForm.bio = account.value?.bio ?? '';
  editingProfile.value = true;
}

async function saveProfile() {
  if (!profileForm.display_name.trim()) {
    uni.showToast({ title: '昵称不能为空', icon: 'none' });
    return;
  }
  try {
    await authApi.updateProfile({
      display_name: profileForm.display_name.trim(),
      bio: profileForm.bio.trim(),
    });
    await authStore.refreshMe();
    editingProfile.value = false;
    uni.showToast({ title: '已保存', icon: 'success' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

async function toggleSessions() {
  showSessions.value = !showSessions.value;
  if (showSessions.value) await loadSessions();
}

async function loadSessions() {
  sessionsLoading.value = true;
  try {
    const res = await authApi.fetchSessions();
    sessions.value = res.items ?? [];
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  } finally {
    sessionsLoading.value = false;
  }
}

function revokeSession(s: LoginSession) {
  uni.showModal({
    title: '下线设备',
    content: `确定让「${s.device_summary || '未知设备'}」下线？该设备的访问令牌与实时连接立即失效。`,
    confirmText: '下线',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await authApi.revokeSession(s.session_id);
        uni.showToast({ title: '已下线', icon: 'none' });
        await loadSessions();
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

function formatTime(iso: string): string {
  return iso ? iso.slice(0, 10) : '';
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
.row-line {
  display: flex;
  align-items: center;
}
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
.field-label {
  font-size: 24rpx;
  color: #8a9099;
  margin: 16rpx 0 8rpx;
}
.textarea {
  width: 100%;
  min-height: 120rpx;
}
.row-gap {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #f0f1f3;
}
.session-item:last-of-type {
  border-bottom: none;
}
.foot-tip {
  margin-top: 20rpx;
  font-size: 22rpx;
  color: #b6bcc4;
}
.foot-note {
  text-align: center;
  color: #b6bcc4;
  font-size: 22rpx;
  margin: 40rpx 0;
}
</style>
