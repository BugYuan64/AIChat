<template>
  <PageLayout title="运行详情" eyebrow="RUN ACTIVITY" subtitle="清楚知道请求进行到哪里，以及下一步可以做什么。" active="sessions" back>
    <InlineNotice v-if="loadError" tone="danger">{{ loadError }}<UiButton variant="ghost" size="small" @click="load">重新加载</UiButton></InlineNotice>
    <view v-else-if="!run" class="panel-hint">正在获取运行状态…</view>
    <view v-if="run" class="detail-grid">
      <view class="panel-stack">
        <SectionPanel :tone="run.state === 'succeeded' ? 'mint' : run.state === 'recovery_required' ? 'violet' : 'default'">
          <view class="run-hero"><view class="run-symbol" :class="{ running: presentation.active }"><UiIcon :name="run.state === 'succeeded' ? 'circle-check' : run.state === 'recovery_required' ? 'triangle-alert' : presentation.active ? 'loader-circle' : 'circle-alert'" :tone="presentation.tone === 'danger' ? 'danger' : 'primary'" :size="34" /></view><view class="data-copy"><text class="run-eyebrow">AI RUN</text><text class="hero-name">{{ presentation.label }}</text><text class="data-description">第 {{ run.attempt_no ?? 1 }} 次尝试</text></view><StatusBadge :tone="presentation.tone" :pulse="presentation.active">{{ presentation.label }}</StatusBadge></view>
          <InlineNotice v-if="run.state === 'recovery_required'" class="run-warning" tone="warning" title="先核实结果，再决定是否重试">连接中断后无法确认最终结果。请检查实际操作是否完成，避免重复执行。</InlineNotice>
          <text v-else class="run-description">{{ presentation.active ? '你的请求正在处理，状态会随实时事件更新。' : run.state === 'succeeded' ? '本次运行已完成，可以回到对话查看回复。' : run.state === 'cancel_requested' ? '停止请求已发送，正在等待运行结束。' : '本次运行已结束。你可以查看原因，或创建一次新的运行。' }}</text>
          <view class="button-row"><UiButton v-if="presentation.active" variant="danger" :loading="actionBusy" @click="cancel">停止运行</UiButton><UiButton v-if="presentation.retryable" :loading="actionBusy" icon="refresh-cw" @click="retry">创建新运行</UiButton><UiButton variant="secondary" icon="refresh-cw" :disabled="actionBusy" @click="load">刷新状态</UiButton><UiButton v-if="run.conversation_id" variant="ghost" icon="message-circle" @click="goConversation">前往会话</UiButton></view>
        </SectionPanel>
        <SectionPanel title="运行时间线" description="展示服务器实际记录的时间。" icon="clock-3">
          <view class="timeline-row"><view class="timeline-dot done" /><view><text class="data-title">请求已创建</text><text class="data-description">{{ run.created_at || '未提供时间' }}</text></view></view>
          <view class="timeline-row"><view class="timeline-dot" :class="{ done: run.started_at }" /><view><text class="data-title">{{ run.started_at ? '开始执行' : '尚未开始执行' }}</text><text class="data-description">{{ run.started_at || '等待运行器接收' }}</text></view></view>
          <view class="timeline-row"><view class="timeline-dot" :class="{ done: run.finished_at }" /><view><text class="data-title">{{ run.finished_at ? presentation.label : presentation.active || run.state === 'cancel_requested' ? '等待最终结果' : presentation.label }}</text><text class="data-description">{{ run.finished_at || '未记录结束时间' }}</text></view></view>
        </SectionPanel>
        <SectionPanel v-if="run.error_code || run.error_message" title="问题详情" icon="circle-alert" tone="danger"><view class="kv"><text class="k">错误码</text><text class="v technical-value">{{ run.error_code || '-' }}</text></view><text class="panel-hint">{{ run.error_message || '暂无补充说明' }}</text></SectionPanel>
      </view>
      <view class="panel-stack">
        <SectionPanel title="运行信息" icon="file-text"><text class="field-label">运行 ID</text><text class="technical-value">{{ run.run_id }}</text><view class="divider" /><text class="field-label">最近更新时间</text><text class="panel-hint">{{ lastUpdate || '未提供' }}</text><view class="button-row"><UiButton variant="secondary" size="small" :icon="techOpen ? 'chevron-down' : 'chevron-right'" @click="techOpen = !techOpen">技术字段</UiButton></view><view v-if="techOpen" class="technical-details"><view v-for="entry in [{ label: '会话', value: run.conversation_id }, { label: 'AI', value: run.agent_id }, { label: '触发消息', value: run.trigger_message_id }, { label: '回复消息', value: run.reply_message_id }, { label: '绑定代际', value: run.binding_generation }]" :key="entry.label" class="technical-entry"><text class="field-label">{{ entry.label }}</text><text class="technical-value">{{ entry.value || '-' }}</text></view></view></SectionPanel>
        <SectionPanel title="关于运行与重试" icon="info" tone="violet"><text class="panel-hint">每次重试都会创建新运行，原有结果会保留。停止属于尽力取消，最终状态以服务器确认为准。</text><view class="divider" /><text class="panel-hint">这里只展示允许公开的运行状态和脱敏信息。</text></SectionPanel>
      </view>
    </view>
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

import { runPresentation } from '../../ui/operations';
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
const techOpen = ref(false);
const actionBusy = ref(false);
const presentation = computed(() => runPresentation(run.value?.state || ''));
const lastUpdate = computed(() => run.value?.updated_at || run.value?.finished_at || run.value?.started_at || run.value?.created_at || '');

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

async function cancel() {
  if (actionBusy.value) return;
  actionBusy.value = true;
  try {
    await runsApi.cancelRun(runId.value);
    chatStore.upsertRun({ run_id: runId.value, state: 'cancel_requested' });
    uni.showToast({ title: '已请求停止（尽力取消）', icon: 'none' });
  } catch (e) {
    loadError.value = describeError(e);
  } finally { actionBusy.value = false; }
}

async function retry() {
  if (actionBusy.value) return;
  if (run.value?.state === 'recovery_required') {
    const result = await uni.showModal({ title: '结果尚不明确', content: '原运行可能已产生实际操作。请先核实原结果，确认后再创建新的运行，避免重复执行。', confirmText: '确认重试' });
    if (!result.confirm) return;
  }
  actionBusy.value = true;
  try {
    const newRun = await runsApi.retryRun(runId.value);
    if (newRun?.run_id) {
      chatStore.upsertRun(newRun);
      uni.showToast({ title: '已创建新运行', icon: 'none' });
      runId.value = newRun.run_id; // 跳转展示新运行
      fetched.value = newRun;
      uni.redirectTo({ url: '/pages/runs/detail?id=' + encodeURIComponent(newRun.run_id) });
    }
  } catch (e) {
    loadError.value = describeError(e);
  } finally { actionBusy.value = false; }
}

function goConversation() {
  if (!run.value?.conversation_id) return;
  uni.navigateTo({ url: `/pages/chat/chat?id=${run.value.conversation_id}` });
}
</script>
<style scoped>.run-hero { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }.run-symbol { width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--line); border-radius: 22px; background: var(--accent-soft); }.run-symbol.running :deep(.ui-icon) { animation: run-spin 3s linear infinite; }@keyframes run-spin { to { transform: rotate(360deg); } }.run-eyebrow { display: block; margin-bottom: 4px; color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: .12em; }.run-description { display: block; margin-top: 22px; font-size: 13px; color: var(--text-secondary); line-height: 1.8; }.run-warning { margin-top: 22px; }.timeline-row { position: relative; display: flex; gap: 16px; padding: 0 0 26px; }.timeline-row:last-child { padding-bottom: 0; }.timeline-row:not(:last-child)::before { content: ''; position: absolute; top: 12px; bottom: 0; left: 5px; width: 1px; background: var(--line-strong); }.timeline-dot { position: relative; z-index: 1; width: 11px; height: 11px; margin-top: 5px; border: 2px solid var(--line-strong); border-radius: 50%; background: var(--surface); }.timeline-dot.done { background: var(--accent); border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }.technical-details { margin-top: 18px; }.technical-entry { margin-top: 16px; }.run-hero .hero-name { font-size: 24px; }@media(max-width:380px){.run-hero > .status-badge { margin-left: 80px; }}</style>
