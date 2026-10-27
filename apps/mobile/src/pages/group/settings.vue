<template>
  <PageLayout title="群聊设置" eyebrow="SHARED SPACE" subtitle="让协作空间保持有序。" active="sessions" back :back-fallback="backFallback">
    <InlineNotice v-if="loadError" tone="danger">{{ loadError }}<UiButton size="small" variant="ghost" @click="load">重新加载</UiButton></InlineNotice>
    <view v-else-if="!detail" class="panel-hint">正在加载群聊…</view>
    <view v-if="detail" class="detail-grid">
      <view class="panel-stack">
        <SectionPanel tone="mint">
          <view class="hero-row"><AccountAvatar :name="detail.title" kind="group" size="large" /><view class="data-copy"><text class="hero-name">{{ detail.title || '群聊' }}</text><text class="data-description">{{ detail.members.length }} 位成员 · {{ closed ? '已归档' : '协作空间' }}</text></view><UiButton v-if="canManage && !closed" variant="secondary" size="small" icon="square-pen" @click="startRename">改名</UiButton></view>
          <view v-if="renaming" class="button-row"><input v-model="renameInput" class="input rename-input" aria-label="新群名称" placeholder="输入新群名" maxlength="128" /><UiButton size="small" @click="confirmRename">保存</UiButton></view>
        </SectionPanel>
        <SectionPanel title="群聊成员" description="群主和管理员负责维护这个空间。" icon="users">
          <template #action><UiButton v-if="canManage && !closed" variant="secondary" size="small" icon="user-plus" @click="invitePickerVisible = true">邀请</UiButton></template>
          <view v-for="m in detail.members" :key="m.membership_id" class="data-row member-row">
            <AccountAvatar :name="m.account.display_name || m.account.handle" :kind="m.account.kind === 'ai' ? 'agent' : 'human'" />
            <view class="data-copy"><text class="data-title">{{ m.account.display_name || m.account.handle }}</text><text class="data-description">@{{ m.account.handle }}</text></view>
            <StatusBadge :tone="m.role === 'owner' ? 'warning' : m.role === 'admin' ? 'primary' : m.account.kind === 'ai' ? 'violet' : 'neutral'">{{ m.role === 'owner' ? '群主' : m.role === 'admin' ? '管理员' : m.account.kind === 'ai' ? 'AI' : '成员' }}</StatusBadge>
            <view v-if="!closed && m.account.account_id !== myAccountId" class="data-actions"><UiButton v-if="canManageRoles(m)" size="small" variant="secondary" @click="openRoleActions(m)">角色</UiButton><UiButton v-if="canManage" size="small" variant="danger" @click="removeMember(m)">移除</UiButton></view>
          </view>
        </SectionPanel>
      </view>
      <view class="panel-stack">
        <SectionPanel title="空间说明" icon="shield-check">
          <text class="panel-hint">人类与 AI 共享对话。AI 加入需其所有者确认，AI 不能担任群主或管理员。</text>
          <view class="divider" /><text class="field-label">会话 ID</text><text class="technical-value">{{ detail.conversation_id }}</text>
        </SectionPanel>
        <SectionPanel v-if="!closed" title="退出与归档" description="操作前请确认对其他成员的影响。" icon="log-out" tone="danger">
          <text v-if="isOwner" class="panel-hint">群主退出前需要转让群主，或解散当前群聊。解散后原成员仍可查看原有可见历史。</text>
          <text v-else class="panel-hint">退出后将不再接收新消息，历史记录保留至退出时刻。</text>
          <view class="button-row"><UiButton v-if="!isOwner" variant="danger" @click="leaveGroup">退出群聊</UiButton><UiButton v-else variant="danger" @click="dissolve">解散群聊</UiButton></view>
        </SectionPanel>
        <InlineNotice v-else>群聊已经解散，当前空间仅保留历史记录。</InlineNotice>
      </view>
    </view>
    <template #overlay>
      <BottomSheet :open="invitePickerVisible" title="邀请联系人加入" @close="invitePickerVisible = false">
        <view class="invite-content"><text class="panel-hint">邀请 AI 时，需要其所有者确认后才能加入。</text>
          <NativeButton v-for="c in invitableContacts" :key="c.account.account_id" class="invite-row" :aria-pressed="inviteIds.includes(c.account.account_id)" @click="toggleInvite(c.account.account_id)"><view class="checkbox" :class="{ checked: inviteIds.includes(c.account.account_id) }"><UiIcon v-if="inviteIds.includes(c.account.account_id)" name="check" tone="inverse" :size="14" /></view><AccountAvatar :name="c.account.display_name || c.account.handle" :kind="c.account.kind === 'ai' ? 'agent' : 'human'" size="small" /><view class="data-copy"><text class="data-title">{{ c.account.display_name || c.account.handle }}</text><text class="data-description">@{{ c.account.handle }}</text></view></NativeButton>
          <EmptyState v-if="!invitableContacts.length" title="没有可邀请的联系人" icon="users" />
        </view>
        <template #footer><UiButton class="wide-button" :disabled="!inviteIds.length" @click="invite">发送 {{ inviteIds.length }} 份邀请</UiButton></template>
      </BottomSheet>
    </template>
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

import { computed, ref } from 'vue';
import { onLoad, onShow } from '@dcloudio/uni-app';
import * as chatApi from '../../api/chat';
import * as contactsApi from '../../api/contacts';
import { useChatStore } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { describeError } from '../../api/client';
import type { BackFallback } from '../../utils/nav';
import type { ContactItem, ConversationDetail, ConversationMember } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const conversationId = ref('');

/** 深链直达时页面栈只有一层，返回键应回到本群聊而不是会话列表 */
const backFallback = computed<BackFallback>(() => conversationId.value
  ? { url: '/pages/chat/chat?id=' + encodeURIComponent(conversationId.value) }
  : { url: '/pages/sessions/sessions', tab: true });
const detail = ref<ConversationDetail | null>(null);
const loadError = ref('');

const invitePickerVisible = ref(false);
const inviteIds = ref<string[]>([]);
const contacts = ref<ContactItem[]>([]);

const myAccountId = computed(() => authStore.myAccountId);
const myMember = computed(() => detail.value?.members.find((m) => m.account.account_id === myAccountId.value));
const isOwner = computed(() => myMember.value?.role === 'owner');
const canManage = computed(() => isOwner.value || myMember.value?.role === 'admin');
const closed = computed(() => !!detail.value?.closed);
const invitableContacts = computed(() => {
  const memberIds = new Set((detail.value?.members ?? []).map((m) => m.account.account_id));
  return contacts.value.filter((c) => c.relation === 'connected' && !memberIds.has(c.account.account_id));
});

onLoad((options) => {
  conversationId.value = options?.id ?? '';
});

onShow(() => {
  if (conversationId.value) void load();
});

async function load() {
  try {
    detail.value = await chatApi.getConversation(conversationId.value);
    loadError.value = '';
    chatStore.cacheAccounts(detail.value.members.map((m) => m.account));
    if (contacts.value.length === 0) {
      const res = await contactsApi.listContacts();
      contacts.value = res.items ?? [];
    }
  } catch (e) {
    loadError.value = describeError(e);
  }
}

function toggleInvite(accountId: string) {
  const i = inviteIds.value.indexOf(accountId);
  if (i >= 0) inviteIds.value.splice(i, 1);
  else inviteIds.value.push(accountId);
}

/* ---- 群改名（群主/管理员） ---- */

const renaming = ref(false);
const renameInput = ref('');

function startRename() {
  renameInput.value = detail.value?.title ?? '';
  renaming.value = true;
}

async function confirmRename() {
  const title = renameInput.value.trim();
  if (!title) {
    uni.showToast({ title: '群名不能为空', icon: 'none' });
    return;
  }
  try {
    await chatApi.renameConversation(conversationId.value, title);
    renaming.value = false;
    uni.showToast({ title: '已修改', icon: 'success' });
    await load();
    await chatStore.loadConversations().catch(() => {});
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

/* ---- 角色管理（仅群主：任免管理员 / 转让群主） ---- */

/** 群主可对其他人类成员操作角色；AI 不可任群主或管理员 */
function canManageRoles(m: ConversationMember): boolean {
  return isOwner.value && m.account.kind === 'human';
}

function openRoleActions(m: ConversationMember) {
  const actions: string[] = [];
  if (m.role === 'admin') actions.push('取消管理员');
  else actions.push('设为管理员');
  actions.push('转让群主');
  uni.showActionSheet({
    itemList: actions,
    success: (res) => {
      const picked = actions[res.tapIndex];
      if (picked === '设为管理员') void applyRole(m, 'admin');
      else if (picked === '取消管理员') void applyRole(m, 'member');
      else confirmTransfer(m);
    },
  });
}

function applyRole(m: ConversationMember, role: 'admin' | 'member') {
  return (async () => {
    try {
      await chatApi.setMemberRole(conversationId.value, m.membership_id, role);
      uni.showToast({ title: role === 'admin' ? '已设为管理员' : '已取消管理员', icon: 'none' });
      await load();
    } catch (e) {
      uni.showToast({ title: describeError(e), icon: 'none' });
    }
  })();
}

function confirmTransfer(m: ConversationMember) {
  uni.showModal({
    title: '转让群主',
    content: `将群主转让给 ${m.account.display_name || m.account.handle}？你将成为普通成员。`,
    confirmText: '转让',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await chatApi.setMemberRole(conversationId.value, m.membership_id, 'owner');
        uni.showToast({ title: '已转让', icon: 'none' });
        await load();
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

async function invite() {
  if (!inviteIds.value.length) return;
  try {
    await chatApi.inviteMembers(conversationId.value, [...inviteIds.value]);
    uni.showToast({ title: '邀请已发送（AI 加入需其所有者确认）', icon: 'none' });
    inviteIds.value = [];
    invitePickerVisible.value = false;
    await load();
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function removeMember(m: ConversationMember) {
  uni.showModal({
    title: '移除成员',
    content: `确定将 ${m.account.display_name || m.account.handle} 移出本群？`,
    confirmText: '移除',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await chatApi.removeMember(conversationId.value, m.membership_id);
        uni.showToast({ title: '已移除', icon: 'none' });
        await load();
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

function leaveGroup() {
  uni.showModal({
    title: '退出群聊',
    content: '退出后不再接收新消息，历史以退出时刻为上限',
    confirmText: '退出',
    success: async (res) => {
      if (!res.confirm || !myMember.value) return;
      try {
        await chatApi.removeMember(conversationId.value, myMember.value.membership_id);
        uni.showToast({ title: '已退出', icon: 'none' });
        await chatStore.loadConversations();
        setTimeout(() => uni.navigateBack({}), 400);
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

function dissolve() {
  uni.showModal({
    title: '解散群聊',
    content: '解散后会话归档，拒绝新消息与任务；原成员保留解散前可见历史。',
    confirmText: '解散',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await chatApi.dissolveConversation(conversationId.value);
        uni.showToast({ title: '已解散', icon: 'none' });
        await chatStore.loadConversations();
        setTimeout(() => uni.navigateBack({}), 400);
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}
</script>
<style scoped>.rename-input { flex: 1; min-width: 0; }.invite-content { padding: 0 20px 20px; }.invite-row { display: flex; align-items: center; gap: 10px; width: 100%; padding: 15px 0; border: 0; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }.invite-row::after { display: none; }.invite-row .checkbox { margin: 0; }@media(max-width:767px){.member-row { flex-wrap: wrap; }.member-row .data-actions { margin-left: auto; }}</style>
