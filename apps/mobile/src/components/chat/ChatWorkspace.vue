<template>
  <view class="chat-page">
    <PageHeader :title="conversationTitle" :subtitle="isGroup ? `${members.length} 位成员 · 团队空间` : 'DIRECT CONVERSATION'" back :action-icon="isGroup ? 'settings-2' : undefined" action-label="群设置" @action="groupSettings" />
    <InlineNotice v-if="pageError" tone="danger">{{ pageError }}</InlineNotice>
    <!-- 消息列表 -->
    <scroll-view
      class="msg-list"
      scroll-y
      :scroll-into-view="scrollInto"
      :upper-threshold="60"
      @scrolltoupper="onScrollToUpper"
      @scroll="onMessageScroll"
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
        <view v-else-if="item.message" class="row" :class="{ mine: isMine(item.message) }" @contextmenu.prevent="onMessageLongPress(item)" @longpress="onMessageLongPress(item)">
          <view v-if="!isMine(item.message)" class="avatar" :class="{ ai: memberKindOf(item.message.sender_account_id) === 'ai', group: isGroup && memberKindOf(item.message.sender_account_id) !== 'ai' }">
            {{ senderInitial(item.message.sender_account_id) }}
          </view>
          <view class="bubble">
            <view v-if="!isMine(item.message) && (isGroup || memberKindOf(item.message.sender_account_id) === 'ai')" class="sender">
              <text>{{ chatStore.memberName(conversationId, item.message.sender_account_id) || '成员' }}</text>
              <text v-if="memberKindOf(item.message.sender_account_id) === 'ai'" class="tag tag-ai">AI</text>
            </view>
            <view v-if="item.message.reply_to_message_id" class="quote">{{ quoteText(item.message.reply_to_message_id) }}</view>
            <view v-if="mentionNames(item.message).length" class="mention-line">
              <text v-for="n in mentionNames(item.message)" :key="n" class="mention-chip">@{{ n }}</text>
            </view>

            <view v-if="isGenerating(item.message)" class="text is-pulsing">{{ generatingText(item.message) }}</view>
            <view v-else class="text">{{ chatStore.renderedTextOf(item.message.message_id) }}</view>

            <!-- AI 运行状态卡（终态成功时不展示） -->
            <view v-if="item.message.run_id && runStateText(item.message)" class="run-card" @tap="goRun(item.message.run_id)">
              <text class="run-state" :class="{ 'is-pulsing': canCancel(item.message) }">{{ runStateText(item.message) }}</text>
              <UiButton variant="ghost" size="small" @click.stop="goRun(item.message.run_id)">运行详情</UiButton>
              <view class="run-actions" v-if="canCancel(item.message) || canRetry(item.message)">
                <UiButton v-if="canCancel(item.message)" variant="secondary" size="small" @click.stop="doCancelRun(item.message.run_id)">停止</UiButton>
                <UiButton v-if="canRetry(item.message)" variant="secondary" size="small" @click.stop="doRetryRun(item.message.run_id)">重试</UiButton>
              </view>
            </view>

            <view class="meta">
              {{ formatTime(item.message.created_at) }}
              <text v-if="item.message.status === 'partial'" class="meta-extra">（生成中）</text>
              <UiButton variant="ghost" size="small" class="message-actions" label="消息操作" @click="onMessageLongPress(item)">操作</UiButton>
            </view>
          </view>
        </view>
      </template>

      <EmptyState v-if="!items.length && !loading && !pageError" icon="message-circle" title="还没有消息" description="发出第一个想法，开始这段对话。" />
      <view v-if="loading" class="loading-tip">加载中…</view>
      <view id="messages-bottom" style="height: 1px" />
    </scroll-view>

    <UiButton v-if="unseenMessages" class="new-messages" variant="secondary" size="small" icon="chevron-down" @click="jumpToLatest">{{ unseenMessages }} 条新消息</UiButton>
    <!-- 正在输入 -->
    <view v-if="typingText" class="typing-bar">{{ typingText }} 正在输入…</view>

    <!-- 会话已关闭 -->
    <view v-if="closed" class="closed-bar">会话已关闭，无法继续发送</view>

    <!-- 引用条 -->
    <view v-if="replyTo && !closed" class="reply-bar">
      <text class="reply-text">回复 {{ replyToName }}：{{ truncate(replyTo.text, 30) }}</text>
      <UiButton variant="ghost" size="icon" icon="x" label="取消引用" @click="replyTo = null" />
    </view>

    <!-- @ 选择提示 -->
    <view v-if="mentionNamesOfSelection.length && !closed" class="reply-bar">
      <text class="reply-text">将触发：{{ mentionNamesOfSelection.join('、') }}</text>
      <UiButton variant="ghost" size="icon" icon="x" label="清除 AI 提及" @click="mentionIds = []" />
    </view>

    <!-- 输入区 -->
    <view class="input-bar" v-if="!closed">
      <UiButton variant="secondary" size="icon" label="选择要提及的 AI" @click="mentionPickerVisible = true">@</UiButton>
      <textarea
        v-model="draft"
        class="input-field"
        :auto-height="true"
        :maxlength="16000"
        :cursor-spacing="16"
        :show-confirm-bar="false"
        placeholder="发一条消息，开始协作…"
        aria-label="消息内容"
        @keydown="composerKeydown"
        @compositionstart="compositionActive = true"
        @compositionend="compositionActive = false"
        @confirm="send()"
      />
      <UiButton icon="send" :disabled="!canSend" label="发送消息" @click="send()">发送</UiButton>
    </view>

    <BottomSheet :open="mentionPickerVisible" title="选择要提及的 AI（最多 3 位）" @close="mentionPickerVisible = false">
      <view class="mention-options">
        <NativeButton v-for="m in aiMembers" :key="m.account_id" class="mention-option" @click="pickMention(m)">
          <AccountAvatar :name="m.display_name || m.handle" kind="agent" size="small" /><view class="data-copy"><text class="data-title">{{ m.display_name || m.handle }}</text><text class="data-description">@{{ m.handle }}</text></view><UiIcon v-if="mentionIds.includes(m.account_id)" name="check" tone="primary" :size="18" />
        </NativeButton>
        <EmptyState v-if="!aiMembers.length" icon="bot" title="本会话暂无 AI 成员" description="AI 私聊无需提及，直接发送即可触发。" />
      </view>
    </BottomSheet>
  </view>
</template>

<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import PageHeader from '../ui/PageHeader.vue';
import BottomSheet from '../ui/BottomSheet.vue';
import NativeButton from '../ui/NativeButton.vue';
import AccountAvatar from '../ui/AccountAvatar.vue';
import EmptyState from '../ui/EmptyState.vue';
import UiIcon from '../ui/UiIcon.vue';
import UiButton from '../ui/UiButton.vue';
import InlineNotice from '../ui/InlineNotice.vue';
import { shouldSendOnEnter, isNearMessageBottom } from '../../ui/chat';
import { sendMessage as sendMessageApi } from '../../api/chat';
import { cancelRun as cancelRunApi, retryRun as retryRunApi } from '../../api/runs';
import { describeError } from '../../api/client';
import { useChatStore, type DisplayItem, type PendingMessage } from '../../stores/chat';
import { useAuthStore } from '../../stores/auth';
import { formatTime, genClientMessageId, truncate } from '../../utils/misc';
import type { DraftReplySnapshot } from '../../utils/drafts';
import type { Message, RunState } from '../../api/types';

const chatStore = useChatStore();
const authStore = useAuthStore();

const props = withDefaults(defineProps<{ id: string; active?: boolean }>(), { active: true });
const conversationId = computed(() => props.id);
const pageError = ref('');
const conversationTitle = computed(() => chatStore.convDetails[conversationId.value]?.title || '对话');
const compositionActive = ref(false);
function composerKeydown(event: KeyboardEvent) { if (!compositionActive.value && shouldSendOnEnter(event)) { event.preventDefault(); void send(); } }
function groupSettings() { uni.navigateTo({ url: '/pages/group/settings?id=' + encodeURIComponent(conversationId.value) }); }
const loading = ref(true);
const scrollInto = ref('');
const component = getCurrentInstance();
const followLatest = ref(true);
const unseenMessages = ref(0);
const listHeight = ref(500);
function measureList() { uni.createSelectorQuery().in(component?.proxy).select('.msg-list').boundingClientRect((rect) => { if (rect && !Array.isArray(rect) && rect.height) listHeight.value = rect.height; }).exec(); }
function onMessageScroll(event: Event) { const detail = (event as unknown as { detail: { scrollTop: number; scrollHeight: number } }).detail; followLatest.value = isNearMessageBottom(detail.scrollTop, detail.scrollHeight, listHeight.value); if (followLatest.value) unseenMessages.value = 0; }
function jumpToLatest() { followLatest.value = true; unseenMessages.value = 0; scrollToBottom(); }
onMounted(() => { measureList(); uni.onWindowResize(measureList); });
onUnmounted(() => uni.offWindowResize(measureList));
const nowTick = ref(Date.now());

const draft = computed({ get: () => chatStore.composerDrafts[props.id]?.text || '', set: (value: string) => chatStore.updateComposerDraft(props.id, { text: value }) });
/** 读出来的是草稿快照（可能来自冷启动恢复），写入可传整条消息，由 store 归一成快照 */
const replyTo = computed<Message | DraftReplySnapshot | null>({
  get: () => chatStore.composerDrafts[props.id]?.reply || null,
  set: (value) => chatStore.updateComposerDraft(props.id, { reply: value }),
});
const mentionIds = computed({ get: () => (chatStore.composerDrafts[props.id]?.mentions || []).map((m) => m.account_id), set: (value: string[]) => chatStore.updateComposerDraft(props.id, { mentions: value }) });
const mentionPickerVisible = ref(false);

const closed = computed(() => !!chatStore.convDetails[conversationId.value]?.closed);
const isGroup = computed(() => chatStore.convDetails[conversationId.value]?.kind === 'group');
const items = computed(() => chatStore.displayListOf(conversationId.value));
const members = computed(() => chatStore.memberListOf(conversationId.value));
const aiMembers = computed(() => members.value.filter((m) => m.kind === 'ai'));
const myAccountId = computed(() => authStore.myAccountId);
const canSend = computed(() => !!draft.value.trim());
const mentionNamesOfSelection = computed(() =>
  (chatStore.composerDrafts[props.id]?.mentions || [])
    .map((m) => chatStore.memberName(conversationId.value, m.account_id) || m.name)
    .filter(Boolean),
);
/** 引用条的名字：优先当前成员数据，冷启动恢复的草稿回落到快照里存的名字 */
const replyToName = computed(() => {
  const r = replyTo.value;
  if (!r) return '';
  const live = 'sender_account_id' in r ? chatStore.memberName(conversationId.value, r.sender_account_id) : '';
  const snapshot = 'sender_account_id' in r ? '' : r.sender_name;
  return live || snapshot || '成员';
});
const typingText = computed(() => {
  void nowTick.value; // 依赖 tick 触发重算
  const names = chatStore.typingOf(conversationId.value);
  return names.length ? names.join('、') : '';
});

let ticker: ReturnType<typeof setInterval> | null = null;

let openVersion = 0;
watch(() => [props.id, props.active] as const, async ([id, active]) => {
  const version = ++openVersion;
  if (!active || !id) { if (chatStore.activeConversationId === id) chatStore.closeConversation(); return; }
  loading.value = true;
  pageError.value = '';
  try {
    await chatStore.openConversation(id);
    if (version !== openVersion) return;
    if (getCurrentPages().at(-1)?.route === 'pages/chat/chat') uni.setNavigationBarTitle({ title: conversationTitle.value });
    await reportRead();
  } catch (e) { if (version === openVersion) pageError.value = describeError(e); }
  finally { if (version === openVersion) { loading.value = false; scrollToBottom(); } }
}, { immediate: true });
ticker = setInterval(() => { nowTick.value = Date.now(); }, 2000);
onUnmounted(() => {
  ++openVersion;
  if (chatStore.activeConversationId === props.id) chatStore.closeConversation();
  if (ticker) clearInterval(ticker);
});

// 新消息到达：滚动到底部并上报已读
watch(
  () => items.value.length,
  (length, previous) => {
    if (loading.value || chatStore.loadingEarlier || !props.active) return;
    nextTick(() => {
      if (followLatest.value) scrollToBottom();
      else unseenMessages.value += Math.max(0, length - previous);
      void reportRead();
    });
  },
);

watch(() => { const last = items.value.at(-1)?.message; return last ? chatStore.renderedTextOf(last.message_id) : ''; }, () => { if (props.active && followLatest.value && !loading.value) scrollToBottom(); });

function scrollToBottom() {
  measureList();
  const last = items.value[items.value.length - 1];
  if (!last) return;
  nextTick(() => {
    scrollInto.value = '';
    nextTick(() => {
      scrollInto.value = 'messages-bottom';
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
  if (!cid || !props.active || chatStore.activeConversationId !== cid) return;
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
    followLatest.value = true;
    unseenMessages.value = 0;
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
  mentionIds.value = [...mentionIds.value, m.account_id];
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
  if (!m) {
    // 历史消息尚未加载时（冷启动恢复的草稿），退回草稿里存的引用快照
    const s = chatStore.composerDrafts[conversationId.value]?.reply;
    if (s && s.message_id === replyId) return `${s.sender_name || '成员'}：${truncate(s.text, 40)}`;
    return '引用的消息未加载';
  }
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

async function doCancelRun(runId?: string) {
  if (!runId) return;
  try {
    await cancelRunApi(runId);
    chatStore.upsertRun({ run_id: runId, state: 'cancel_requested' });
    uni.showToast({ title: '已请求停止（尽力取消）', icon: 'none' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

async function doRetryRun(runId?: string) {
  if (!runId) return;
  try {
    const run = await retryRunApi(runId);
    if (run?.run_id) chatStore.upsertRun(run);
    uni.showToast({ title: '已重新发起（旧结果保留）', icon: 'none' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function goRun(runId?: string) {
  if (!runId) return;
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

<style scoped lang="scss">
.chat-page { display: flex; flex-direction: column; height: 100%; min-height: 0; background: radial-gradient(ellipse at 90% 0%, rgba(226,240,230,.5), transparent 50%), var(--canvas); }
.msg-list { flex: 1; height: 0; min-height: 0; padding: 16px 0; box-sizing: border-box; }
.sys-tip { margin: 12px auto; padding: 7px 13px; width: fit-content; max-width: 84%; border: 1px solid var(--line); border-radius: 30px; color: var(--text-secondary); background: var(--surface-soft); font-size: 11px; text-align: center; }
.row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 20px; animation: ui-rise 240ms var(--ease-out) both; }
.row .avatar { width: 34px; height: 34px; border-radius: 12px; font-size: 12px; }
.row.mine { justify-content: flex-end; }
.bubble { max-width: min(80%, 650px); padding: 14px 17px; border: 1px solid var(--line); border-radius: 5px 20px 20px; background: var(--surface-elevated); box-shadow: 0 4px 14px rgba(25,45,34,.035); }
.row.mine .bubble { border-color: #c9ddcd; border-radius: 20px 5px 20px 20px; background: var(--accent-soft); }
.sender { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; color: var(--text-secondary); font-size: 11px; font-weight: 700; }
.quote { margin-bottom: 10px; padding: 8px 10px; border-left: 3px solid var(--accent); border-radius: 7px; background: var(--surface-soft); color: var(--text-secondary); font-size: 11px; line-height: 1.5; }
.mention-line { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }.mention-chip { border-radius: 5px; padding: 3px 6px; background: var(--violet-soft); color: var(--violet); font-size: 11px; }
.text { font-size: 14px; line-height: 1.75; word-break: break-word; white-space: pre-wrap; }
.meta { display: flex; align-items: center; gap: 6px; margin-top: 8px; color: var(--text-secondary); font-size: 10px; }
.state-failed { color: var(--danger); }.run-card { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px; margin-top: 12px; background: var(--surface-soft); border: 1px solid var(--line); border-radius: 12px; }.run-state { color: var(--text-secondary); font-size: 11px; }.run-actions { display: flex; gap: 6px; }
.typing-bar { padding: 8px 24px; color: var(--accent); font-size: 12px; animation: ui-pulse 1.8s infinite; }
.closed-bar { padding: 16px; color: var(--text-secondary); background: var(--surface-soft); font-size: 13px; text-align: center; }
.reply-bar { display: flex; align-items: center; gap: 8px; padding: 4px 16px; background: var(--surface); border-top: 1px solid var(--line); }.reply-text { flex: 1; min-width: 0; color: var(--text-secondary); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.input-bar { display: flex; align-items: flex-end; gap: 10px; margin: 10px 18px 18px; padding: 10px; border: 1px solid var(--line-strong); border-radius: 20px; background: var(--surface); box-shadow: var(--shadow-soft); }
.input-field { flex: 1; min-width: 0; min-height: 44px; max-height: 160px; padding: 11px 4px; border: 0; border-radius: 10px; color: var(--text); background: transparent; font-size: 14px; line-height: 1.6; }
@media (max-width: 767px) { .row { padding: 8px 12px; }.bubble { max-width: 84%; padding: 12px; }.input-bar { margin: 8px 10px calc(10px + env(safe-area-inset-bottom)); gap: 7px; }.row .avatar { display: none; } }
.mention-options { padding: 0 20px 20px; }.mention-option { display: flex; width: 100%; align-items: center; gap: 12px; min-height: 68px; padding: 12px 0; border: 0; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }.message-actions { min-height: 28px; padding: 0 7px; font-size: 10px; }
.new-messages { align-self: center; position: relative; z-index: 5; margin-top: -44px; margin-bottom: 8px; box-shadow: var(--shadow-soft); }
</style>
