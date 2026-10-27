<template>
  <PageLayout title="我的空间" eyebrow="PERSONAL SPACE" subtitle="让你的身份、设备与 AI 各就其位。" active="me">
    <view class="detail-grid">
      <view class="panel-stack">
        <SectionPanel tone="mint">
          <view class="hero-row"><AccountAvatar :name="account?.display_name || account?.handle" size="large" /><view class="data-copy"><text class="hero-name">{{ account?.display_name || account?.handle || '未登录' }}</text><text class="data-description">@{{ account?.handle || '-' }} · 人类账号</text></view><UiButton variant="secondary" size="small" icon="square-pen" @click="startEditProfile">编辑</UiButton></view>
          <text v-if="account?.bio" class="profile-bio">{{ account.bio }}</text>
        </SectionPanel>
        <SectionPanel title="AI 与设备" description="建立自己的 AI 搭档，连接熟悉的工作环境。" icon="sparkles">
          <NativeButton class="menu-link" @click="go('/pages/agents/agents')"><view class="menu-icon"><UiIcon name="bot" tone="primary" /></view><view class="data-copy"><text class="data-title">我的 AI</text><text class="data-description">管理 AI 身份、模型与使用授权</text></view><UiIcon name="chevron-right" tone="muted" :size="18" /></NativeButton>
          <NativeButton class="menu-link" @click="go('/pages/pairing/scan')"><view class="menu-icon violet"><UiIcon name="scan-line" tone="primary" /></view><view class="data-copy"><text class="data-title">连接设备</text><text class="data-description">扫码或输入配对码接入连接器</text></view><UiIcon name="chevron-right" tone="muted" :size="18" /></NativeButton>
        </SectionPanel>
        <SectionPanel title="账号安全" icon="shield-check">
          <NativeButton class="menu-link" @click="toggleSessions"><view class="menu-icon"><UiIcon name="lock-keyhole" tone="primary" /></view><view class="data-copy"><text class="data-title">登录会话</text><text class="data-description">查看设备，撤销不再使用的登录</text></view><UiIcon :name="showSessions ? 'chevron-down' : 'chevron-right'" tone="muted" :size="18" /></NativeButton>
          <view v-if="showSessions" class="sessions-panel motion-enter">
            <InlineNotice v-if="sessionsError" tone="danger">{{ sessionsError }}<UiButton size="small" variant="ghost" @click="loadSessions">重试</UiButton></InlineNotice>
            <text v-if="sessionsLoading" class="panel-hint">正在加载登录设备…</text>
            <view v-for="s in sessions" :key="s.session_id" class="data-row"><view class="data-copy"><text class="data-title">{{ s.device_summary || '未知设备' }}</text><text class="data-description">登录于 {{ formatTime(s.created_at) }}</text></view><StatusBadge v-if="s.current" tone="primary">本机</StatusBadge><UiButton v-else size="small" variant="danger" @click="revokeSession(s)">下线</UiButton></view>
            <EmptyState v-if="!sessionsLoading && !sessionsError && !sessions.length" title="暂无活跃会话" icon="lock-keyhole" />
          </view>
        </SectionPanel>
      </view>
      <view class="panel-stack">
        <SectionPanel title="连接设置" description="当前客户端使用的服务器地址" icon="server">
          <text class="technical-value">{{ serverBase }}</text><view class="button-row"><UiButton variant="secondary" size="small" @click="showServer = !showServer">{{ showServer ? '收起' : '更改地址' }}</UiButton></view>
          <view v-if="showServer" class="server-form motion-enter"><input v-model="serverBaseInput" class="input" aria-label="服务器地址" placeholder="https://chat.example.com" /><InlineNotice v-if="serverError" tone="danger">{{ serverError }}</InlineNotice><UiButton size="small" @click="saveServerBase">保存地址</UiButton></view>
        </SectionPanel>
        <SectionPanel title="关于这个空间" tone="violet" icon="message-circle"><text class="panel-hint">AIChat 让人类与 AI 在同一个对话空间协作。应用在前台接收实时消息，回到前台后自动补齐。</text></SectionPanel>
        <SectionPanel title="退出登录" description="清除当前客户端的登录状态与消息缓存。" tone="danger"><UiButton variant="danger" icon="log-out" @click="logout">退出当前账号</UiButton></SectionPanel>
      </view>
    </view>
    <template #overlay><BottomSheet :open="editingProfile" title="编辑个人资料" @close="editingProfile = false"><view class="edit-profile"><InlineNotice v-if="profileError" tone="danger">{{ profileError }}</InlineNotice><view class="field"><label class="field-label">昵称</label><input v-model="profileForm.display_name" class="input" aria-label="昵称" placeholder="你希望大家如何称呼你" maxlength="128" /></view><view class="field"><label class="field-label">简介</label><textarea v-model="profileForm.bio" class="textarea" aria-label="简介" placeholder="写一句话介绍自己" maxlength="2048" /></view></view><template #footer><UiButton class="wide-button" @click="saveProfile">保存资料</UiButton></template></BottomSheet></template>
  </PageLayout>
</template>
<script setup lang="ts">
import PageLayout from '../../components/layout/PageLayout.vue';
import SectionPanel from '../../components/ui/SectionPanel.vue';
import UiButton from '../../components/ui/UiButton.vue';
import NativeButton from '../../components/ui/NativeButton.vue';
import UiIcon from '../../components/ui/UiIcon.vue';
import AccountAvatar from '../../components/ui/AccountAvatar.vue';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import InlineNotice from '../../components/ui/InlineNotice.vue';
import EmptyState from '../../components/ui/EmptyState.vue';
import BottomSheet from '../../components/ui/BottomSheet.vue';

import { computed, reactive, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import * as authApi from '../../api/auth';
import type { LoginSession } from '../../api/types';
import { describeError, getServerBase, setServerBase } from '../../api/client';

const authStore = useAuthStore();

const showServer = ref(false);
const serverError = ref('');
const sessionsError = ref('');
const profileError = ref('');
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
    profileError.value = '昵称不能为空';
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
    profileError.value = describeError(e);
  }
}

async function toggleSessions() {
  showSessions.value = !showSessions.value;
  if (showSessions.value) await loadSessions();
}

async function loadSessions() {
  sessionsLoading.value = true;
  sessionsError.value = '';
  try {
    const res = await authApi.fetchSessions();
    sessions.value = res.items ?? [];
  } catch (e) {
    sessionsError.value = describeError(e);
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
  serverError.value = '';
  try {
    const normalized = setServerBase(serverBaseInput.value);
    serverBase.value = normalized;
    uni.showToast({ title: '已保存', icon: 'success' });
  } catch (e) {
    serverError.value = describeError(e);
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
<style scoped>.profile-bio { display: block; margin-top: 20px; font-size: 14px; line-height: 1.7; color: var(--text-secondary); }.menu-link { display: flex; width: 100%; align-items: center; gap: 13px; min-height: 80px; margin: 0; padding: 12px 0; border: 0; border-bottom: 1px solid var(--line); background: transparent; text-align: left; transition: transform 140ms; }.menu-link:hover { transform: translateX(3px); }.menu-link::after { display: none; }.menu-link:last-child { border-bottom: 0; }.menu-icon { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border: 1px solid #cbdcc9; border-radius: 15px; background: var(--accent-soft); }.menu-icon.violet { background: var(--violet-soft); border-color: #d9ceea; }.edit-profile { padding: 0 22px 20px; }.server-form { display: flex; flex-direction: column; gap: 12px; margin-top: 18px; }.sessions-panel { padding-top: 12px; border-top: 1px solid var(--line); }</style>
