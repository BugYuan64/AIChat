<template>
  <view class="page">
    <!-- 搜索（按账号名精确查找） -->
    <view class="card search-card">
      <view class="search-row">
        <input v-model="searchHandle" class="input" placeholder="输入对方账号名（handle）精确查找" confirm-type="search" @confirm="doSearch" />
        <view class="btn btn-primary btn-small" @tap="doSearch">查找</view>
      </view>
      <view v-if="searchResult" class="search-result enter-rise">
        <view class="list-body">
          <view class="row-line">
            <text class="list-title">{{ searchResult.display_name || searchResult.handle }}</text>
            <text :class="['tag', searchResult.kind === 'ai' ? 'tag-ai' : '']">{{ searchResult.kind === 'ai' ? 'AI' : '人类' }}</text>
          </view>
          <view class="list-sub">@{{ searchResult.handle }}</view>
        </view>
        <view class="list-end">
          <view class="btn btn-primary btn-small" @tap="addContact(searchResult)">加联系人</view>
          <view class="btn btn-ghost btn-small" @tap="openDirect(searchResult)">发消息</view>
        </view>
      </view>
      <view v-if="searchMiss" class="list-sub">未找到该账号（需精确匹配账号名）</view>
    </view>

    <!-- 分栏：联系人 / 待处理申请 -->
    <view class="segmented">
      <text :class="['seg-item', segment === 'list' ? 'active' : '']" @tap="switchSegment('list')">
        联系人 {{ contacts.length ? `(${contacts.length})` : '' }}
      </text>
      <text :class="['seg-item', segment === 'requests' ? 'active' : '']" @tap="switchSegment('requests')">
        待处理 {{ incoming.length ? `(${incoming.length})` : '' }}
      </text>
    </view>

    <!-- 建群入口 -->
    <view v-if="segment === 'list' && !selectMode" class="group-entry enter-rise" @tap="enterSelectMode">
      发起群聊（从联系人中选择成员）
    </view>

    <!-- 联系人列表 -->
    <view v-if="segment === 'list'">
      <view v-if="loading && !contacts.length" class="card">
        <view v-for="i in 3" :key="'sk' + i" class="skeleton-row">
          <view class="skeleton skeleton-avatar"></view>
          <view class="skeleton-lines">
            <view class="skeleton skeleton-line l1"></view>
            <view class="skeleton skeleton-line l2"></view>
          </view>
        </view>
      </view>
      <view v-if="!contacts.length && !loading" class="empty">还没有联系人,先通过上方搜索添加</view>

      <!-- 普通模式 -->
      <view v-if="!selectMode" class="stagger">
        <view v-for="item in contacts" :key="item.account.account_id" class="list-item">
          <view :class="['avatar', item.account.kind === 'ai' ? 'ai' : '']">
            {{ (item.account.display_name || item.account.handle || '?').slice(0, 1).toUpperCase() }}
          </view>
          <view class="list-body" @tap="openDirect(item.account)">
            <view class="row-line">
              <text class="list-title">{{ item.account.display_name || item.account.handle }}</text>
              <text :class="['tag', item.account.kind === 'ai' ? 'tag-ai' : '']">{{ item.account.kind === 'ai' ? 'AI' : '人类' }}</text>
              <text v-if="item.relation === 'pending_outgoing'" class="tag">已申请</text>
            </view>
            <view class="list-sub">@{{ item.account.handle }}</view>
          </view>
          <view class="list-end">
            <view v-if="item.relation === 'connected'" class="btn btn-ghost btn-small" @tap="openDirect(item.account)">发消息</view>
            <view class="btn btn-ghost btn-small" @tap="moreActions(item)">···</view>
          </view>
        </view>
      </view>

      <!-- 建群多选模式 -->
      <view v-else class="stagger">
        <view
          v-for="item in connectedContacts"
          :key="item.account.account_id"
          class="list-item"
          @tap="toggleSelect(item.account.account_id)"
        >
          <view class="checkbox" :class="{ checked: selectedIds.includes(item.account.account_id) }">
            {{ selectedIds.includes(item.account.account_id) ? '✓' : '' }}
          </view>
          <view class="list-body">
            <view class="row-line">
              <text class="list-title">{{ item.account.display_name || item.account.handle }}</text>
              <text :class="['tag', item.account.kind === 'ai' ? 'tag-ai' : '']">{{ item.account.kind === 'ai' ? 'AI' : '人类' }}</text>
            </view>
            <view class="list-sub">@{{ item.account.handle }}</view>
          </view>
        </view>
        <view v-if="!connectedContacts.length" class="empty">没有可选联系人</view>
      </view>
    </view>

    <!-- 待处理申请 -->
    <view v-if="segment === 'requests'" class="stagger">
      <view v-if="!incoming.length && !outgoing.length && !loading" class="empty">暂无待处理申请</view>
      <view class="section-title">收到的申请</view>
      <view v-for="item in incoming" :key="item.account.account_id" class="list-item">
        <view class="avatar">{{ (item.account.display_name || item.account.handle || '?').slice(0, 1).toUpperCase() }}</view>
        <view class="list-body">
          <view class="row-line">
            <text class="list-title">{{ item.account.display_name || item.account.handle }}</text>
            <text :class="['tag', item.account.kind === 'ai' ? 'tag-ai' : '']">{{ item.account.kind === 'ai' ? 'AI（所有者代批）' : '人类' }}</text>
          </view>
          <view class="list-sub">@{{ item.account.handle }}</view>
        </view>
        <view class="list-end">
          <view class="btn btn-primary btn-small" @tap="decide(item, 'accept')">接受</view>
          <view class="btn btn-ghost btn-small" @tap="decide(item, 'reject')">拒绝</view>
        </view>
      </view>
      <view class="section-title">我发出的申请</view>
      <view v-for="item in outgoing" :key="item.account.account_id" class="list-item">
        <view class="avatar">{{ (item.account.display_name || item.account.handle || '?').slice(0, 1).toUpperCase() }}</view>
        <view class="list-body">
          <text class="list-title">{{ item.account.display_name || item.account.handle }}</text>
          <view class="list-sub">@{{ item.account.handle }} · 等待对方处理</view>
        </view>
      </view>
    </view>

    <!-- 建群底栏 -->
    <view v-if="selectMode" class="group-bar">
      <input v-model="groupTitle" class="input group-title-input" placeholder="群名称" :maxlength="64" />
      <view class="btn btn-ghost btn-small" @tap="exitSelectMode">取消</view>
      <view class="btn btn-primary btn-small" :class="{ 'btn-disabled': !groupTitle.trim() || !selectedIds.length }" @tap="createGroup">
        创建（{{ selectedIds.length }}）
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app';
import * as contactsApi from '../../api/contacts';
import * as chatApi from '../../api/chat';
import { useChatStore } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { describeError } from '../../api/client';
import { genClientMessageId } from '../../utils/misc';
import type { AccountBrief, ContactItem } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const loading = ref(false);
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
  try {
    const res = await contactsApi.listContacts();
    items.value = res.items ?? [];
    chatStore.cacheAccounts(items.value.map((i) => i.account));
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
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
  if (!h) {
    uni.showToast({ title: '请输入账号名', icon: 'none' });
    return;
  }
  try {
    searchResult.value = await contactsApi.findAccountByHandle(h);
  } catch (e) {
    searchMiss.value = true;
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

<style lang="scss" scoped>
.search-card {
  padding: 24rpx;
}
.search-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  .input {
    flex: 1;
  }
}
.search-result {
  display: flex;
  align-items: center;
  margin-top: 24rpx;
  padding: 20rpx;
  background: var(--surface-soft);
  border-radius: 20rpx;
}
.row-line {
  display: flex;
  align-items: center;
  min-width: 0;
}
.group-entry {
  margin: 0 24rpx 24rpx;
  padding: 26rpx;
  border-radius: 20rpx;
  background: var(--surface);
  color: var(--accent);
  font-size: 26rpx;
  text-align: center;
  border: 1rpx dashed var(--control-line);
}
.group-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 20rpx 24rpx calc(20rpx + env(safe-area-inset-bottom));
  background: var(--surface);
  border-top: 1rpx solid var(--line);
  z-index: 99;
}
.group-title-input {
  flex: 1;
}
/* H5 桌面:底栏跟随居中内容列 */
@media (min-width: 768px) {
  .group-bar {
    max-width: 720px;
    margin: 0 auto;
  }
}
</style>
