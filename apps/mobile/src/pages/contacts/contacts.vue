<template>
  <PageLayout title="联系人" eyebrow="PEOPLE & CONNECTIONS" subtitle="找到伙伴，让对话自然发生。" active="contacts">
    <template #actions><UiButton icon="users" @click="enterSelectMode">创建群聊</UiButton></template>
    <view class="contacts-layout">
      <view class="panel-stack">
        <SectionPanel title="添加新伙伴" description="按完整账号名精确查找" icon="user-plus" tone="mint">
          <input v-model="searchHandle" class="input" aria-label="查找账号名" placeholder="输入对方的账号名" confirm-type="search" @confirm="doSearch" />
          <UiButton class="wide-button search-button" icon="search" @click="doSearch">查找账号</UiButton>
          <text class="panel-hint search-hint">人类或 AI 都可以成为联系人。AI 联系申请由其所有者处理。</text>
          <InlineNotice v-if="searchError" tone="danger">{{ searchError }}</InlineNotice>
          <InlineNotice v-if="searchMiss">没有找到这个账号，请检查完整账号名。</InlineNotice>
        </SectionPanel>
        <view class="contact-tabs">
          <NativeButton class="contact-tab" :class="{ active: segment === 'list' }" @click="switchSegment('list')"><UiIcon name="users" :size="18" /><text>我的联系人</text><text class="tab-count">{{ contacts.length }}</text></NativeButton>
          <NativeButton class="contact-tab" :class="{ active: segment === 'requests' }" @click="switchSegment('requests')"><UiIcon name="user-plus" :size="18" /><text>联系人申请</text><text v-if="incoming.length" class="tab-count request-count">{{ incoming.length }}</text></NativeButton>
        </view>
      </view>
      <SectionPanel :title="segment === 'list' ? '一起协作的人与 AI' : '连接请求'" :description="segment === 'list' ? '从一条消息开始新的协作。' : '收到与发出的申请都在这里。'">
        <InlineNotice v-if="pageError" tone="danger">{{ pageError }}<UiButton variant="ghost" size="small" @click="refresh">重新加载</UiButton></InlineNotice>
        <view v-if="searchResult" class="search-match">
          <StatusBadge tone="success" icon="check">找到账号</StatusBadge>
          <view class="data-row"><AccountAvatar :name="searchResult.display_name || searchResult.handle" :kind="searchResult.kind === 'ai' ? 'agent' : 'human'" /><view class="data-copy"><text class="data-title">{{ searchResult.display_name || searchResult.handle }}</text><text class="data-description">@{{ searchResult.handle }}</text></view></view>
          <view class="button-row"><UiButton size="small" icon="user-plus" @click="addContact(searchResult)">添加联系人</UiButton><UiButton size="small" variant="secondary" icon="message-circle" @click="openDirect(searchResult)">发消息</UiButton></view>
        </view>
        <view v-if="loading" class="panel-hint">正在同步联系人…</view>
        <template v-if="segment === 'list'">
          <view v-for="item in contacts" :key="item.account.account_id" class="data-row contact-row">
            <AccountAvatar :name="item.account.display_name || item.account.handle" :kind="item.account.kind === 'ai' ? 'agent' : 'human'" />
            <view class="data-copy"><text class="data-title">{{ item.account.display_name || item.account.handle }}</text><text class="data-description">@{{ item.account.handle }}</text></view>
            <StatusBadge v-if="item.relation === 'pending_outgoing'" tone="warning">已申请</StatusBadge>
            <StatusBadge v-else-if="item.account.kind === 'ai'" tone="violet">AI</StatusBadge>
            <view class="data-actions"><UiButton v-if="item.relation === 'connected'" variant="ghost" size="icon" icon="message-circle" :label="'向' + item.account.handle + '发消息'" @click="openDirect(item.account)" /><UiButton variant="ghost" size="icon" icon="ellipsis" :label="item.account.handle + '的更多操作'" @click="moreActions(item)" /></view>
          </view>
          <EmptyState v-if="!loading && !pageError && !contacts.length" icon="users" title="在这里遇见协作伙伴" description="在左侧或上方搜索账号，添加你的第一位联系人。" />
        </template>
        <template v-else>
          <text class="request-heading">收到的申请</text>
          <view v-for="item in incoming" :key="item.request_id" class="data-row contact-row"><AccountAvatar :name="item.account.display_name || item.account.handle" :kind="item.account.kind === 'ai' ? 'agent' : 'human'" /><view class="data-copy"><text class="data-title">{{ item.account.display_name || item.account.handle }}</text><text class="data-description">@{{ item.account.handle }}{{ item.account.kind === 'ai' ? ' · AI 所有者代批' : '' }}</text></view><view class="data-actions"><UiButton size="small" @click="decide(item, 'accept')">接受</UiButton><UiButton variant="secondary" size="small" @click="decide(item, 'reject')">拒绝</UiButton></view></view>
          <EmptyState v-if="!incoming.length && !loading" icon="circle-check" title="暂无待处理申请" />
          <text class="request-heading">我发出的申请</text>
          <view v-for="item in outgoing" :key="item.account.account_id" class="data-row"><AccountAvatar :name="item.account.display_name || item.account.handle" /><view class="data-copy"><text class="data-title">{{ item.account.display_name || item.account.handle }}</text><text class="data-description">等待对方处理</text></view><StatusBadge tone="warning">等待中</StatusBadge></view>
        </template>
      </SectionPanel>
    </view>
    <template #overlay>
      <BottomSheet :open="selectMode" title="创建群聊" @close="exitSelectMode">
        <view class="group-form"><label class="field-label">给群聊起个名字</label><input v-model="groupTitle" class="input" placeholder="例如：周末项目组" aria-label="群名称" :maxlength="64" /><text class="panel-hint">选择要邀请的联系人，邀请会在创建后发送。</text>
          <NativeButton v-for="item in connectedContacts" :key="item.account.account_id" class="pick-row" :aria-pressed="selectedIds.includes(item.account.account_id)" @click="toggleSelect(item.account.account_id)"><view class="checkbox" :class="{ checked: selectedIds.includes(item.account.account_id) }"><UiIcon v-if="selectedIds.includes(item.account.account_id)" name="check" tone="inverse" :size="14" /></view><AccountAvatar :name="item.account.display_name || item.account.handle" :kind="item.account.kind === 'ai' ? 'agent' : 'human'" size="small" /><view class="data-copy"><text class="data-title">{{ item.account.display_name || item.account.handle }}</text><text class="data-description">@{{ item.account.handle }}</text></view></NativeButton>
          <EmptyState v-if="!connectedContacts.length" icon="users" title="还没有可邀请的联系人" />
        </view>
        <template #footer><UiButton class="wide-button" :disabled="!groupTitle.trim() || !selectedIds.length" @click="createGroup">创建并邀请 {{ selectedIds.length }} 位成员</UiButton></template>
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
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app';
import * as contactsApi from '../../api/contacts';
import * as chatApi from '../../api/chat';
import { useChatStore } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { describeError, ApiClientError } from '../../api/client';
import { genClientMessageId } from '../../utils/misc';
import type { AccountBrief, ContactItem } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const loading = ref(false);
const pageError = ref('');
const searchError = ref('');
const segment = ref<'list' | 'requests'>('list');
const items = ref<ContactItem[]>([]);

const searchHandle = ref('');
const searchResult = ref<AccountBrief | null>(null);
const searchMiss = ref(false);

const selectMode = ref(false);
const selectedIds = ref<string[]>([]);
const groupTitle = ref('');

const contacts = computed(() => items.value.filter((i) => i.relation === 'connected' || i.relation === 'pending_outgoing'));
const connectedContacts = computed(() => items.value.filter((i) => i.relation === 'connected'));
const incoming = computed(() => items.value.filter((i) => i.relation === 'pending_incoming'));
const outgoing = computed(() => items.value.filter((i) => i.relation === 'pending_outgoing'));

onShow(async () => {
  if (!authStore.isLoggedIn) return;
  if (chatStore.requestGroupCreate) {
    chatStore.requestGroupCreate = false;
    segment.value = 'list';
    enterSelectMode();
  }
  await refresh();
});

onPullDownRefresh(async () => {
  await refresh();
  uni.stopPullDownRefresh();
});

async function refresh() {
  loading.value = true;
  pageError.value = '';
  try {
    const res = await contactsApi.listContacts();
    items.value = res.items ?? [];
    chatStore.cacheAccounts(items.value.map((i) => i.account));
  } catch (e) {
    pageError.value = describeError(e);
  } finally {
    loading.value = false;
  }
}

function switchSegment(s: 'list' | 'requests') {
  if (selectMode.value) exitSelectMode();
  segment.value = s;
}

/* ---------------- 精确查找与申请 ---------------- */

async function doSearch() {
  const h = searchHandle.value.trim();
  searchResult.value = null;
  searchMiss.value = false;
  searchError.value = '';
  if (!h) {
    uni.showToast({ title: '请输入账号名', icon: 'none' });
    return;
  }
  try {
    searchResult.value = await contactsApi.findAccountByHandle(h);
  } catch (e) {
    if (e instanceof ApiClientError && e.code === 'NOT_FOUND') searchMiss.value = true;
    else searchError.value = describeError(e);
  }
}

async function addContact(account: AccountBrief) {
  try {
    await contactsApi.sendContactRequest(account.account_id);
    uni.showToast({
      title: account.kind === 'ai' ? '已申请，等待其所有者批准' : '已发送申请',
      icon: 'none',
    });
    await refresh();
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

async function decide(item: ContactItem, decision: 'accept' | 'reject') {
  if (!item.request_id) {
    uni.showToast({ title: '缺少申请 ID，请下拉刷新', icon: 'none' });
    return;
  }
  try {
    await contactsApi.decideContactRequest(item.request_id, decision);
    uni.showToast({ title: decision === 'accept' ? '已接受' : '已拒绝', icon: 'none' });
    await refresh();
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function moreActions(item: ContactItem) {
  uni.showActionSheet({
    itemList: ['移除联系人', '拉黑该账号'],
    success: async (res) => {
      try {
        if (res.tapIndex === 0) {
          await contactsApi.removeContact(item.account.account_id);
          uni.showToast({ title: '已移除（历史保留）', icon: 'none' });
        } else {
          await contactsApi.blockContact(item.account.account_id);
          uni.showToast({ title: '已拉黑', icon: 'none' });
        }
        await refresh();
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

/* ---------------- 私聊 ---------------- */

async function openDirect(account: AccountBrief) {
  try {
    const conv = await chatApi.createDirectConversation(account.account_id, genClientMessageId());
    chatStore.cacheAccounts([account]);
    uni.navigateTo({ url: `/pages/chat/chat?id=${conv.conversation_id}` });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

/* ---------------- 建群 ---------------- */

function enterSelectMode() {
  selectMode.value = true;
  selectedIds.value = [];
  groupTitle.value = '';
}

function exitSelectMode() {
  selectMode.value = false;
  selectedIds.value = [];
  groupTitle.value = '';
}

function toggleSelect(accountId: string) {
  const i = selectedIds.value.indexOf(accountId);
  if (i >= 0) selectedIds.value.splice(i, 1);
  else selectedIds.value.push(accountId);
}

async function createGroup() {
  const title = groupTitle.value.trim();
  if (!title || !selectedIds.value.length) return;
  try {
    const conv = await chatApi.createGroup(title, [...selectedIds.value]);
    uni.showToast({ title: '群已创建，邀请待对方确认', icon: 'none' });
    exitSelectMode();
    await chatStore.loadConversations();
    uni.navigateTo({ url: `/pages/chat/chat?id=${conv.conversation_id}` });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}
</script>
<style scoped>
.contacts-layout { display: grid; grid-template-columns: minmax(0,1fr); gap: 24px; }.search-button { margin-top: 12px; }.search-hint { margin: 16px 0 0; }.contact-tabs { display: flex; gap: 6px; flex-direction: column; }.contact-tab { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 48px; padding: 0 14px; border: 1px solid transparent; border-radius: 14px; background: transparent; color: var(--text-secondary); text-align: left; font-size: 13px; font-weight: 650; }.contact-tab.active { background: var(--surface); border-color: var(--line); color: var(--text); }.tab-count { margin-left: auto; font-size: 11px; }.request-count { background: var(--violet-soft); color: var(--violet); padding: 3px 8px; border-radius: 30px; }.search-match { padding: 16px; margin-bottom: 18px; border: 1px solid #c6d7bf; border-radius: 16px; background: var(--accent-soft); }.request-heading { display: block; margin-top: 16px; color: var(--text-secondary); font-size: 12px; font-weight: 700; }.group-form { padding: 0 20px 20px; }.group-form > .panel-hint { margin: 12px 0; }.pick-row { width: 100%; display: flex; align-items: center; gap: 10px; min-height: 70px; padding: 10px 0; border: 0; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }.pick-row::after { display: none; }.pick-row .checkbox { margin: 0; }
@media(min-width:1100px) { .contacts-layout { grid-template-columns: 280px minmax(0,1fr); } }@media(max-width:380px) { .contact-row { flex-wrap: wrap; }.contact-row .data-actions { margin-left: auto; } }
</style>
