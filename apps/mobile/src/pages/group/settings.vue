<template>
  <view class="page">
    <view v-if="!detail && !loadError" class="empty">加载中…</view>
    <view v-else-if="loadError" class="empty">{{ loadError }}</view>

    <template v-if="detail">
      <!-- 群信息 -->
      <view class="card">
        <view class="row-line">
          <view class="group-title">{{ detail.title || '群聊' }}</view>
          <text v-if="canManage && !closed" class="rename-btn" @tap="startRename">改名</text>
        </view>
        <view class="list-sub">
          {{ detail.kind === 'group' ? '群聊' : '私聊' }} · {{ detail.members.length }} 名成员
          <text v-if="closed" class="tag tag-offline">已解散</text>
        </view>
        <view class="list-sub">ID：{{ detail.conversation_id }}</view>
        <view v-if="renaming" class="rename-box">
          <input v-model="renameInput" class="input" placeholder="新群名（1-128 字符）" maxlength="128" />
          <view class="btn btn-primary btn-small" @tap="confirmRename">保存</view>
        </view>
      </view>

      <!-- 成员 -->
      <view class="section-title">成员（角色：群主 / 管理员 / 成员；AI 不可任群主或管理员）</view>
      <view
        v-for="m in detail.members"
        :key="m.membership_id"
        class="list-item"
      >
        <view :class="['avatar', m.account.kind === 'ai' ? 'ai' : '']">
          {{ (m.account.display_name || m.account.handle || '?').slice(0, 1).toUpperCase() }}
        </view>
        <view class="list-body">
          <view class="row-line">
            <text class="list-title">{{ m.account.display_name || m.account.handle }}</text>
            <text v-if="m.account.kind === 'ai'" class="tag tag-ai">AI</text>
            <text v-if="m.role === 'owner'" class="tag tag-owner">群主</text>
            <text v-else-if="m.role === 'admin'" class="tag tag-admin">管理员</text>
          </view>
          <view class="list-sub">@{{ m.account.handle }}</view>
        </view>
        <view
          class="list-end member-actions"
          v-if="!closed && m.account.account_id !== myAccountId"
        >
          <view v-if="canManage" class="btn btn-danger btn-small" @tap="removeMember(m)">移除</view>
          <text v-if="canManageRoles(m)" class="role-btn" @tap="openRoleActions(m)">角色</text>
        </view>
      </view>

      <!-- 操作 -->
      <view class="card" v-if="!closed">
        <view v-if="canManage" class="btn btn-primary" @tap="invitePickerVisible = true">邀请成员</view>
        <view v-if="!isOwner" class="btn btn-ghost" @tap="leaveGroup">退出群聊</view>
        <view v-else class="btn btn-ghost btn-disabled">群主退出前需转让群主或解散群</view>
        <view v-if="isOwner" class="btn btn-danger" @tap="dissolve">解散群聊</view>
      </view>
    </template>

    <!-- 邀请选择 -->
    <view v-if="invitePickerVisible" class="mask" @tap="invitePickerVisible = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-title">选择要邀请的联系人（邀请 AI 需其所有者确认）</view>
        <scroll-view scroll-y class="sheet-list">
          <view
            v-for="c in invitableContacts"
            :key="c.account.account_id"
            class="list-item"
            @tap="toggleInvite(c.account.account_id)"
          >
            <view class="checkbox" :class="{ checked: inviteIds.includes(c.account.account_id) }">
              {{ inviteIds.includes(c.account.account_id) ? '✓' : '' }}
            </view>
            <view class="list-body">
              <view class="row-line">
                <text class="list-title">{{ c.account.display_name || c.account.handle }}</text>
                <text v-if="c.account.kind === 'ai'" class="tag tag-ai">AI</text>
              </view>
              <view class="list-sub">@{{ c.account.handle }}</view>
            </view>
          </view>
          <view v-if="!invitableContacts.length" class="empty">没有可邀请的联系人</view>
        </scroll-view>
        <view class="sheet-footer">
          <view class="btn btn-ghost btn-small" @tap="invitePickerVisible = false">取消</view>
          <view class="btn btn-primary btn-small" :class="{ 'btn-disabled': !inviteIds.length }" @tap="invite">
            发送邀请（{{ inviteIds.length }}）
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onLoad, onShow } from '@dcloudio/uni-app';
import * as chatApi from '../../api/chat';
import * as contactsApi from '../../api/contacts';
import { useChatStore } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { describeError } from '../../api/client';
import type { ContactItem, ConversationDetail, ConversationMember } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const conversationId = ref('');
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

<style lang="scss" scoped>
.row-line {
  display: flex;
  align-items: center;
}
.group-title {
  font-size: 34rpx;
  font-weight: 600;
}
.rename-btn {
  margin-left: auto;
  font-size: 24rpx;
  color: #3b82f6;
  padding: 4rpx 12rpx;
}
.rename-box {
  display: flex;
  gap: 16rpx;
  align-items: center;
  margin-top: 20rpx;
  .input {
    flex: 1;
  }
}
.member-actions {
  display: flex;
  align-items: center;
  gap: 16rpx;
}
.role-btn {
  font-size: 24rpx;
  color: #3b82f6;
  padding: 8rpx 16rpx;
}
.checkbox {
  width: 40rpx;
  height: 40rpx;
  border-radius: 10rpx;
  border: 2rpx solid #cbd5e1;
  margin-right: 20rpx;
  color: #ffffff;
  font-size: 26rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.checkbox.checked {
  background: #3b82f6;
  border-color: #3b82f6;
}
.sheet-footer {
  display: flex;
  gap: 16rpx;
  padding: 20rpx 24rpx;
  justify-content: flex-end;
}
</style>
