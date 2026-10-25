<template>
  <view class="chat-page">
    <!-- 消息列表 -->
    <scroll-view
      class="msg-list"
      scroll-y
      :scroll-into-view="scrollInto"
      :upper-threshold="60"
      @scrolltoupper="onScrollToUpper"
    >
      <view v-if="chatStore.loadingEarlier" class="loading-tip">加载中…</view>
      <view v-else-if="!chatStore.hasMore[conversationId] && items.length" class="loading-tip">没有更多消息了</view>

      <template v-for="item in items" :key="item.key">
        <view :id="`anchor-${item.key}`"></view>

        <!-- 系统消息（灰条） -->
        <view v-if="item.message && item.message.kind === 'system'" class="sys-tip">{{ item.message.text }}</view>

        <!-- 本地待发 -->
        <view v-else-if="item.pending" class="row mine">
          <view class="bubble">
            <view v-if="item.pending.reply_to_message_id" class="quote">{{ quoteText(item.pending.reply_to_message_id) }}</view>
            <view class="text">{{ item.pending.text }}</view>
            <view class="meta">
              <text v-if="item.pending.state === 'sending'" class="state-sending">发送中…</text>
              <text v-else class="state-failed" @tap="send(item.pending)">发送失败，点击重试</text>
            </view>
          </view>
        </view>

        <!-- 服务端消息 -->
        <view v-else-if="item.message" class="row" :class="{ mine: isMine(item.message) }" @longpress="onMessageLongPress(item)">
          <view v-if="!isMine(item.message)" class="avatar" :class="{ ai: memberKindOf(item.message.sender_account_id) === 'ai' }">
            {{ senderInitial(item.message.sender_account_id) }}
          </view>
          <view class="bubble">
            <view v-if="!isMine(item.message) && isGroup" class="sender">
              {{ chatStore.memberName(conversationId, item.message.sender_account_id) || '成员' }}
            </view>
            <view v-if="item.message.reply_to_message_id" class="quote">{{ quoteText(item.message.reply_to_message_id) }}</view>
            <view v-if="mentionNames(item.message).length" class="mention-line">
              <text v-for="n in mentionNames(item.message)" :key="n" class="mention-chip">@{{ n }}</text>
            </view>

            <view v-if="isGenerating(item.message)" class="text">{{ generatingText(item.message) }}</view>
            <view v-else class="text">{{ chatStore.renderedTextOf(item.message.message_id) }}</view>

            <!-- AI 运行状态卡（终态成功时不展示） -->
            <view v-if="item.message.run_id && runStateText(item.message)" class="run-card" @tap="goRun(item.message.run_id)">
              <text class="run-state">{{ runStateText(item.message) }}</text>
              <view class="run-actions" v-if="canCancel(item.message) || canRetry(item.message)">
                <view v-if="canCancel(item.message)" class="mini-btn" @tap.stop="doCancelRun(item.message.run_id!)">停止</view>
                <view v-if="canRetry(item.message)" class="mini-btn" @tap.stop="doRetryRun(item.message.run_id!)">重试</view>
              </view>
            </view>

            <view class="meta">
              {{ formatTime(item.message.created_at) }}
              <text v-if="item.message.status === 'partial'" class="meta-extra">（生成中）</text>
            </view>
          </view>
        </view>
      </template>

      <view v-if="!items.length && !loading" class="empty">还没有消息，发一条开始对话吧</view>
      <view v-if="loading" class="loading-tip">加载中…</view>
    </scroll-view>

    <!-- 正在输入 -->
    <view v-if="typingText" class="typing-bar">{{ typingText }} 正在输入…</view>

    <!-- 会话已关闭 -->
    <view v-if="closed" class="closed-bar">会话已关闭，无法继续发送</view>

    <!-- 引用条 -->
    <view v-if="replyTo && !closed" class="reply-bar">
      <text class="reply-text">回复 {{ chatStore.memberName(conversationId, replyTo.sender_account_id) || '成员' }}：{{ truncate(replyTo.text, 30) }}</text>
      <text class="reply-cancel" @tap="replyTo = null">✕</text>
    </view>

    <!-- @ 选择提示 -->
    <view v-if="mentionNamesOfSelection.length && !closed" class="reply-bar">
      <text class="reply-text">将触发：{{ mentionNamesOfSelection.join('、') }}</text>
      <text class="reply-cancel" @tap="mentionIds = []">✕</text>
    </view>

    <!-- 输入区 -->
    <view class="input-bar" v-if="!closed">
      <view class="icon-btn" @tap="mentionPickerVisible = true">@</view>
      <textarea
        v-model="draft"
        class="input-field"
        :auto-height="true"
        :maxlength="16000"
        :cursor-spacing="16"
        :show-confirm-bar="false"
        placeholder="输入消息…"
        @confirm="send()"
      />
      <view class="send-btn" :class="{ disabled: !canSend }" @tap="send()">发送</view>
    </view>

    <!-- @ 成员选择（仅 AI 成员） -->
    <view v-if="mentionPickerVisible" class="mask" @tap="mentionPickerVisible = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-title">选择要 @ 的 AI 成员（最多 3 个）</view>
        <scroll-view scroll-y class="sheet-list">
          <view v-for="m in aiMembers" :key="m.account_id" class="list-item" @tap="pickMention(m)">
            <view class="avatar ai">{{ (m.display_name || 'A').slice(0, 1).toUpperCase() }}</view>
            <view class="list-body">
              <view class="list-title">{{ m.display_name || m.handle }}</view>
              <view class="list-sub">@{{ m.handle }}</view>
            </view>
            <view v-if="mentionIds.includes(m.account_id)" class="list-end link">已选</view>
          </view>
          <view v-if="!aiMembers.length" class="empty">本会话暂无 AI 成员（私聊无需 @，直接发送即可触发）</view>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app';
import { sendMessage as sendMessageApi } from '../../api/chat';
import { cancelRun as cancelRunApi, retryRun as retryRunApi } from '../../api/runs';
import { describeError } from '../../api/client';
import { useChatStore, type DisplayItem, type PendingMessage } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { formatTime, genClientMessageId, truncate } from '../../utils/misc';
import type { Message, RunState } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const conversationId = ref('');
const loading = ref(true);
const scrollInto = ref('');
const nowTick = ref(Date.now());

const draft = ref('');
const replyTo = ref<Message | null>(null);
const mentionIds = ref<string[]>([]);
const mentionPickerVisible = ref(false);

const closed = computed(() => !!chatStore.convDetails[conversationId.value]?.closed);
const isGroup = computed(() => chatStore.convDetails[conversationId.value]?.kind === 'group');
const items = computed(() => chatStore.displayListOf(conversationId.value));
const members = computed(() => chatStore.memberListOf(conversationId.value));
const aiMembers = computed(() => members.value.filter((m) => m.kind === 'ai'));
const myAccountId = computed(() => authStore.myAccountId);
const canSend = computed(() => !!draft.value.trim());
const mentionNamesOfSelection = computed(() =>
  mentionIds.value.map((id) => chatStore.memberName(conversationId.value, id)).filter(Boolean),
);
const typingText = computed(() => {
  void nowTick.value; // 依赖 tick 触发重算
  const names = chatStore.typingOf(conversationId.value);
  return names.length ? names.join('、') : '';
});

let ticker: ReturnType<typeof setInterval> | null = null;

onLoad(async (options) => {
  const id = options?.id ?? '';
  if (!id) {
    uni.showToast({ title: '缺少会话参数', icon: 'none' });
    setTimeout(() => uni.navigateBack({}), 600);
    return;
  }
  conversationId.value = id;
  loading.value = true;
  try {
    await chatStore.openConversation(id);
    const title = chatStore.convDetails[id]?.title;
    if (title) uni.setNavigationBarTitle({ title });
    await reportRead();
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  } finally {
    loading.value = false;
    scrollToBottom();
  }
  ticker = setInterval(() => {
    nowTick.value = Date.now();
  }, 2000);
});

onShow(() => {
  chatStore.activeConversationId = conversationId.value || chatStore.activeConversationId;
  void reportRead();
});

onHide(() => {
  chatStore.closeConversation();
});

onUnload(() => {
  chatStore.closeConversation();
  if (ticker) clearInterval(ticker);
});

// 新消息到达：滚动到底部并上报已读
watch(
  () => items.value.length,
  () => {
    nextTick(() => {
      scrollToBottom();
      void reportRead();
    });
  },
);

function scrollToBottom() {
  const last = items.value[items.value.length - 1];
  if (!last) return;
  nextTick(() => {
    scrollInto.value = '';
    nextTick(() => {
      scrollInto.value = `anchor-${last.key}`;
    });
  });
}

/* ---------------- 历史分页（上拉到顶加载更早） ---------------- */

async function onScrollToUpper() {
  const cid = conversationId.value;
  if (!cid || chatStore.loadingEarlier || !chatStore.hasMore[cid]) return;
  const firstBefore = (chatStore.messages[cid] ?? [])[0]?.message_id;
  await chatStore.loadEarlierMessages(cid);
  if (firstBefore) {
    // 锚定到加载前的首条，避免滚动位置跳动
    nextTick(() => {
      scrollInto.value = `anchor-${firstBefore}`;
    });
  }
}

/* ---------------- 已读上报（through_seq 只前进） ---------------- */

async function reportRead() {
  const cid = conversationId.value;
  if (!cid) return;
  const list = chatStore.messages[cid] ?? [];
  const last = list[list.length - 1];
  if (last) await chatStore.markRead(cid, last.seq);
}

/* ---------------- 发送（client_message_id 幂等，失败重试沿用） ---------------- */

async function send(retryPending?: PendingMessage) {
  const cid = conversationId.value;
  if (!cid || closed.value) return;

  let clientId: string;
  let text: string;
  let mentions: string[];
  let replyToId: string | undefined;

  if (retryPending) {
    clientId = retryPending.client_message_id; // 重试沿用同一幂等键，避免重复记录
    text = retryPending.text;
    mentions = retryPending.mentions;
    replyToId = retryPending.reply_to_message_id;
    chatStore.setPendingState(cid, clientId, 'sending');
  } else {
    text = draft.value.trim();
    if (!text) return;
    if (mentionIds.value.length > 3) {
      uni.showToast({ title: '单条消息最多 @ 3 个 AI', icon: 'none' });
      return;
    }
    clientId = genClientMessageId();
    mentions = [...mentionIds.value];
    replyToId = replyTo.value?.message_id;
    chatStore.addPending({
      client_message_id: clientId,
      conversation_id: cid,
      text,
      mentions,
      reply_to_message_id: replyToId,
      state: 'sending',
    });
    draft.value = '';
    replyTo.value = null;
    mentionIds.value = [];
  }
  scrollToBottom();

  try {
    const res = await sendMessageApi(cid, {
      client_message_id: clientId,
      text,
      mentions: mentions.length ? mentions : undefined,
      reply_to_message_id: replyToId,
    });
    chatStore.removePending(cid, clientId);
    chatStore.upsertMessage(res.message);
    (res.runs ?? []).forEach((r) => chatStore.upsertRun(r));
    nextTick(() => {
      scrollToBottom();
      void reportRead();
    });
  } catch (e) {
    chatStore.setPendingState(cid, clientId, 'failed');
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

/* ---------------- @ 选择（仅 AI 成员） ---------------- */

function pickMention(m: { account_id: string }) {
  if (mentionIds.value.includes(m.account_id)) {
    mentionIds.value = mentionIds.value.filter((x) => x !== m.account_id);
    return;
  }
  if (mentionIds.value.length >= 3) {
    uni.showToast({ title: '最多 @ 3 个 AI', icon: 'none' });
    return;
  }
  mentionIds.value.push(m.account_id);
  const handle = chatStore.memberName(conversationId.value, m.account_id);
  if (handle) draft.value = `${draft.value}@${handle} `;
  mentionPickerVisible.value = false;
}

/* ---------------- 渲染辅助 ---------------- */

function isMine(m: Message): boolean {
  return m.sender_account_id === myAccountId.value;
}

function senderInitial(accountId: string): string {
  const name = chatStore.memberName(conversationId.value, accountId) || chatStore.displayNameOf(accountId) || '?';
  return name.slice(0, 1).toUpperCase();
}

function memberKindOf(accountId: string): string {
  return chatStore.members[conversationId.value]?.[accountId]?.kind ?? chatStore.accountCache[accountId]?.kind ?? '';
}

function mentionNames(m: Message): string[] {
  return (m.mentions ?? [])
    .map((id) => chatStore.memberName(conversationId.value, id) || chatStore.displayNameOf(id))
    .filter(Boolean);
}

function quoteText(replyId?: string): string {
  if (!replyId) return '';
  const m = (chatStore.messages[conversationId.value] ?? []).find((x) => x.message_id === replyId);
  if (!m) return '引用的消息未加载';
  const name = chatStore.memberName(conversationId.value, m.sender_account_id) || '成员';
  return `${name}：${truncate(m.text, 40)}`;
}

/** 生成中：draft 尚无任何输出时显示占位 */
function isGenerating(m: Message): boolean {
  const text = chatStore.renderedTextOf(m.message_id);
  return m.status !== 'final' && !text;
}

function generatingText(m: Message): string {
  return m.status === 'draft' ? '正在思考…' : '生成中…';
}

/* ---------------- 运行状态卡 ---------------- */

function runStateText(m: Message): string {
  const run = chatStore.runOf(m.run_id);
  const state = run?.state as RunState | undefined;
  if (m.status === 'final' && (state === 'succeeded' || !state)) return '';
  switch (state) {
    case 'queued':
    case 'dispatched':
      return '排队等待中';
    case 'running':
      return '运行中';
    case 'cancel_requested':
      return '正在停止…';
    case 'succeeded':
      return '已完成';
    case 'failed':
      return `失败${run?.error_code ? `（${run.error_code}）` : ''}，点击查看`;
    case 'cancelled':
      return '已停止';
    case 'expired':
      return '已超时';
    case 'recovery_required':
      return '结果未知，需人工处理';
  }
  if (m.status === 'draft') return '正在生成';
  if (m.status === 'partial') return '生成中';
  return '';
}

function canCancel(m: Message): boolean {
  const s = chatStore.runOf(m.run_id)?.state;
  return s === 'queued' || s === 'dispatched' || s === 'running';
}

function canRetry(m: Message): boolean {
  const s = chatStore.runOf(m.run_id)?.state;
  return s === 'failed' || s === 'cancelled' || s === 'expired';
}

async function doCancelRun(runId: string) {
  try {
    await cancelRunApi(runId);
    chatStore.upsertRun({ run_id: runId, state: 'cancel_requested' });
    uni.showToast({ title: '已请求停止（尽力取消）', icon: 'none' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

async function doRetryRun(runId: string) {
  try {
    const run = await retryRunApi(runId);
    if (run?.run_id) chatStore.upsertRun(run);
    uni.showToast({ title: '已重新发起（旧结果保留）', icon: 'none' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function goRun(runId: string) {
  uni.navigateTo({ url: `/pages/runs/detail?id=${runId}` });
}

/* ---------------- 长按操作 ---------------- */

function onMessageLongPress(item: DisplayItem) {
  if (item.pending) {
    if (item.pending.state === 'failed') {
      uni.showActionSheet({
        itemList: ['重试发送', '复制文本'],
        success: (r) => {
          if (r.tapIndex === 0) void send(item.pending);
          else if (r.tapIndex === 1) copy(item.pending!.text);
        },
      });
    } else {
      uni.showActionSheet({
        itemList: ['复制文本'],
        success: () => copy(item.pending!.text),
      });
    }
    return;
  }
  const m = item.message;
  if (!m || m.kind === 'system') return;
  const actions = ['引用回复', '复制文本'];
  const canRegen = canRetry(m);
  if (canRegen) actions.push('让 AI 重新回答');
  uni.showActionSheet({
    itemList: actions,
    success: (r) => {
      const action = actions[r.tapIndex];
      if (action === '引用回复') replyTo.value = m;
      else if (action === '复制文本') copy(m.text);
      else if (action === '让 AI 重新回答' && m.run_id) void doRetryRun(m.run_id);
    },
  });
}

function copy(text: string) {
  uni.setClipboardData({ data: text, showToast: false });
  uni.showToast({ title: '已复制', icon: 'none' });
}
</script>

<style lang="scss" scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f6f7;
  box-sizing: border-box;
}
.msg-list {
  flex: 1;
  height: 0;
  padding: 16rpx 0;
  box-sizing: border-box;
}
.sys-tip {
  align-self: center;
  margin: 16rpx auto;
  padding: 8rpx 24rpx;
  background: #e8eaee;
  color: #8a9099;
  border-radius: 999rpx;
  font-size: 22rpx;
  max-width: 80%;
  text-align: center;
}
.row {
  display: flex;
  padding: 12rpx 24rpx;
  align-items: flex-start;
}
.row .avatar {
  width: 68rpx;
  height: 68rpx;
  border-radius: 14rpx;
  font-size: 28rpx;
  margin-right: 16rpx;
}
.row.mine {
  justify-content: flex-end;
}
.bubble {
  max-width: 76%;
  background: #ffffff;
  border-radius: 4rpx 20rpx 20rpx 20rpx;
  padding: 18rpx 22rpx;
}
.row.mine .bubble {
  background: #3b82f6;
  color: #ffffff;
  border-radius: 20rpx 4rpx 20rpx 20rpx;
}
.sender {
  font-size: 22rpx;
  color: #8a9099;
  margin-bottom: 8rpx;
}
.quote {
  font-size: 22rpx;
  color: #6b7480;
  background: #f2f3f5;
  border-left: 4rpx solid #cbd5e1;
  border-radius: 8rpx;
  padding: 8rpx 14rpx;
  margin-bottom: 10rpx;
}
.row.mine .quote {
  background: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
  border-left-color: rgba(255, 255, 255, 0.6);
}
.mention-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-bottom: 8rpx;
}
.mention-chip {
  font-size: 20rpx;
  color: #3b82f6;
  background: #eff6ff;
  border-radius: 6rpx;
  padding: 2rpx 10rpx;
}
.row.mine .mention-chip {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.2);
}
.text {
  font-size: 28rpx;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}
.meta {
  margin-top: 8rpx;
  font-size: 20rpx;
  color: #b0b6bf;
  display: flex;
  gap: 8rpx;
  align-items: center;
}
.state-sending {
  color: #b0b6bf;
}
.state-failed {
  color: #f87171;
}
.run-card {
  margin-top: 12rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
  background: #f8fafc;
  border-radius: 10rpx;
  padding: 10rpx 16rpx;
}
.row.mine .run-card {
  background: rgba(255, 255, 255, 0.18);
}
.run-state {
  font-size: 22rpx;
  color: #5b6472;
}
.row.mine .run-state {
  color: rgba(255, 255, 255, 0.95);
}
.run-actions {
  display: flex;
  gap: 12rpx;
}
.mini-btn {
  font-size: 22rpx;
  color: #3b82f6;
  border: 1rpx solid #93c5fd;
  border-radius: 999rpx;
  padding: 4rpx 18rpx;
}
.row.mine .mini-btn {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.7);
}
.typing-bar {
  padding: 8rpx 32rpx;
  font-size: 22rpx;
  color: #8a9099;
}
.closed-bar {
  padding: 16rpx 32rpx calc(16rpx + env(safe-area-inset-bottom));
  text-align: center;
  font-size: 24rpx;
  color: #b0b6bf;
  background: #eef0f3;
}
.reply-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14rpx 32rpx;
  background: #ffffff;
  border-top: 1rpx solid #f0f1f3;
}
.reply-text {
  flex: 1;
  font-size: 24rpx;
  color: #5b6472;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reply-cancel {
  padding: 0 12rpx;
  color: #9aa0a6;
}
.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 16rpx;
  padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #ffffff;
  border-top: 1rpx solid #f0f1f3;
}
.icon-btn {
  width: 68rpx;
  height: 68rpx;
  border-radius: 14rpx;
  background: #f2f3f5;
  color: #3b82f6;
  font-size: 32rpx;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.input-field {
  flex: 1;
  background: #f2f3f5;
  border-radius: 14rpx;
  padding: 16rpx 20rpx;
  font-size: 28rpx;
  min-height: 40rpx;
  max-height: 240rpx;
  line-height: 1.4;
  box-sizing: border-box;
}
.send-btn {
  height: 68rpx;
  padding: 0 32rpx;
  border-radius: 14rpx;
  background: #3b82f6;
  color: #ffffff;
  font-size: 28rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.send-btn.disabled {
  opacity: 0.5;
}
</style>
