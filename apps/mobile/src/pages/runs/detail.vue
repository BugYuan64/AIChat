<template>
  <view class="page">
    <view v-if="!run && !loadError" class="empty">加载中…</view>
    <view v-else-if="loadError" class="empty">{{ loadError }}</view>

    <template v-if="run">
      <view class="card">
        <view class="state-row">
          <text :class="['state-chip', stateClass(run.state)]">{{ stateText(run.state) }}</text>
          <text class="attempt">第 {{ run.attempt_no ?? '-' }} 次尝试</text>
        </view>
        <view class="kv"><text class="k">运行 ID</text><text class="v">{{ run.run_id }}</text></view>
        <view class="kv"><text class="k">会话</text><text class="v">{{ run.conversation_id }}</text></view>
        <view class="kv"><text class="k">AI</text><text class="v">{{ run.agent_id }}</text></view>
        <view class="kv"><text class="k">触发消息</text><text class="v">{{ run.trigger_message_id }}</text></view>
        <view v-if="run.reply_message_id" class="kv"><text class="k">回复消息</text><text class="v">{{ run.reply_message_id }}</text></view>
        <view class="kv"><text class="k">创建时间</text><text class="v">{{ run.created_at || '-' }}</text></view>
        <view class="kv"><text class="k">开始时间</text><text class="v">{{ run.started_at || '-' }}</text></view>
        <view class="kv"><text class="k">结束时间</text><text class="v">{{ run.finished_at || '-' }}</text></view>
        <view v-if="run.binding_generation" class="kv"><text class="k">绑定代际</text><text class="v">{{ run.binding_generation }}</text></view>
      </view>

      <view v-if="run.error_code || run.error_message" class="card fail-card">
        <view class="fail-title">失败原因（脱敏）</view>
        <view class="kv"><text class="k">错误码</text><text class="v">{{ run.error_code || '-' }}</text></view>
        <view class="kv"><text class="k">说明</text><text class="v">{{ run.error_message || '-' }}</text></view>
        <view class="foot-tip">工具调用与推理内部过程不会发布为聊天内容；此处仅展示允许公开的脱敏摘要。</view>
      </view>

      <view class="card">
        <view v-if="isActive(run.state)" class="btn btn-danger" @tap="cancel">停止运行（尽力取消）</view>
        <view v-if="isRetryable(run.state)" class="btn btn-primary" @tap="retry">重试（创建新运行，保留旧结果）</view>
        <view class="btn btn-ghost" @tap="load">刷新</view>
        <view v-if="run.conversation_id" class="btn" @tap="goConversation">前往会话</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onLoad, onShow } from '@dcloudio/uni-app';
import * as runsApi from '../../api/runs';
import { useChatStore } from '../../stores/chat';
import { describeError } from '../../api/client';
import type { Run, RunState } from '../../api/types';

const chatStore = useChatStore();

const runId = ref('');
const fetched = ref<Run | null>(null);
const loadError = ref('');

/** 优先取事件实时维护的运行状态，回退到 HTTP 快照 */
const run = computed<Run | null>(() => chatStore.runOf(runId.value) ?? fetched.value);

onLoad((options) => {
  runId.value = options?.id ?? '';
});

onShow(() => {
  if (runId.value) void load();
});

async function load() {
  try {
    fetched.value = await runsApi.getRun(runId.value);
    chatStore.upsertRun(fetched.value);
    loadError.value = '';
  } catch (e) {
    loadError.value = describeError(e);
  }
}

function isActive(s: RunState): boolean {
  return s === 'queued' || s === 'dispatched' || s === 'running' || s === 'cancel_requested';
}

function isRetryable(s: RunState): boolean {
  return s === 'failed' || s === 'cancelled' || s === 'expired' || s === 'recovery_required';
}

function stateText(s: RunState): string {
  switch (s) {
    case 'queued':
      return '排队中';
    case 'dispatched':
      return '已派发';
    case 'running':
      return '运行中';
    case 'cancel_requested':
      return '取消中';
    case 'succeeded':
      return '已完成';
    case 'failed':
      return '失败';
    case 'cancelled':
      return '已取消';
    case 'expired':
      return '已超时';
    case 'recovery_required':
      return '结果未知（需人工处理）';
    default:
      return s;
  }
}

function stateClass(s: RunState): string {
  if (s === 'succeeded') return 'ok';
  if (s === 'failed' || s === 'expired' || s === 'recovery_required') return 'bad';
  if (s === 'cancelled' || s === 'cancel_requested') return 'warn';
  return 'run';
}

async function cancel() {
  try {
    await runsApi.cancelRun(runId.value);
    chatStore.upsertRun({ run_id: runId.value, state: 'cancel_requested' });
    uni.showToast({ title: '已请求停止（尽力取消）', icon: 'none' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

async function retry() {
  try {
    const newRun = await runsApi.retryRun(runId.value);
    if (newRun?.run_id) {
      chatStore.upsertRun(newRun);
      uni.showToast({ title: '已创建新运行', icon: 'none' });
      runId.value = newRun.run_id; // 跳转展示新运行
      fetched.value = newRun;
    }
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function goConversation() {
  if (!run.value?.conversation_id) return;
  uni.navigateTo({ url: `/pages/chat/chat?id=${run.value.conversation_id}` });
}
</script>

<style lang="scss" scoped>
.state-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-bottom: 16rpx;
}
.state-chip {
  font-size: 24rpx;
  padding: 8rpx 20rpx;
  border-radius: 999rpx;
}
.state-chip.run {
  background: #dbeafe;
  color: #1d4ed8;
}
.state-chip.ok {
  background: #dcfce7;
  color: #16a34a;
}
.state-chip.bad {
  background: #fee2e2;
  color: #dc2626;
}
.state-chip.warn {
  background: #fef3c7;
  color: #b45309;
}
.attempt {
  font-size: 24rpx;
  color: #8a9099;
}
.kv {
  display: flex;
  padding: 10rpx 0;
  font-size: 26rpx;
}
.kv .k {
  width: 170rpx;
  color: #8a9099;
  flex-shrink: 0;
}
.kv .v {
  flex: 1;
  word-break: break-all;
}
.fail-card {
  background: #fef2f2;
}
.fail-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 8rpx;
}
.foot-tip {
  margin-top: 16rpx;
  font-size: 22rpx;
  color: #b6bcc4;
}
</style>
