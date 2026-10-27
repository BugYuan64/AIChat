<template>
  <PageLayout title="我的 AI" eyebrow="YOUR AI TEAM" subtitle="每一位搭档，都有自己的身份和能力。" active="agents" back>
    <template #actions><UiButton icon="plus" @click="createVisible = true">创建 AI</UiButton></template>
    <view class="ai-intro"><view><text class="ai-intro-title">把你的 AI 搭档，<br />带进每一次协作。</text><text class="ai-intro-description">绑定模型 API，或连接外部设备。用独立身份，加入真实对话。</text></view><view class="ai-intro-art"><UiIcon name="bot" tone="primary" :size="40" /><view class="art-spark"><UiIcon name="sparkles" :size="18" /></view></view></view>
    <InlineNotice v-if="pageError" tone="danger">{{ pageError }}<UiButton variant="ghost" size="small" @click="load()">重新加载</UiButton></InlineNotice>
    <view v-if="loading && !agents.length" class="panel-hint">正在加载 AI 档案…</view>
    <view class="agent-grid motion-list">
      <NativeButton v-for="a in agents" :key="a.agent_id" class="agent-card" @click="openDetail(a)">
        <view class="agent-card-top"><AccountAvatar :name="a.display_name" kind="agent" size="large" /><StatusBadge :tone="a.online ? 'success' : 'neutral'" :pulse="a.online">{{ a.online ? '在线' : '离线' }}</StatusBadge></view>
        <text class="agent-name">{{ a.display_name }}</text><text class="agent-handle">@{{ a.handle }}</text>
        <text class="agent-bio">{{ a.bio || '为你的协作空间带来新的可能。' }}</text>
        <view class="agent-binding"><UiIcon :name="a.binding?.mode === 'connector' ? 'link-2' : 'bot'" tone="muted" :size="15" /><text>{{ bindingLine(a) }}</text><UiIcon name="chevron-right" tone="muted" :size="16" /></view>
      </NativeButton>
    </view>
    <EmptyState v-if="!agents.length && !loading && !pageError" icon="bot" title="遇见你的第一位 AI 搭档" description="先创建 AI 账号，再选择模型 API 或连接器接入。" action-label="创建 AI" @action="createVisible = true" />
    <template #overlay><BottomSheet :open="createVisible" title="创建新的 AI 搭档" @close="createVisible = false"><view class="create-form"><view class="field"><label class="field-label">AI 名称</label><input v-model="form.display_name" class="input" aria-label="AI 名称" placeholder="例如：研究搭档" :maxlength="64" /></view><view class="field"><label class="field-label">唯一账号名</label><input v-model="form.handle" class="input" aria-label="AI 账号名" placeholder="用于识别与添加联系人" :maxlength="64" /></view><view class="field"><label class="field-label">简介</label><textarea v-model="form.bio" class="textarea" aria-label="AI 简介" placeholder="这个 AI 擅长做什么？" :maxlength="500" /></view><text class="panel-hint">创建后，需要为 AI 绑定模型 API 或连接器。</text></view><template #footer><UiButton class="wide-button" :loading="creating" @click="create">创建搭档</UiButton></template></BottomSheet></template>
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

import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import * as agentsApi from '../../api/agents';
import { useChatStore } from '../../stores/chat';
import { describeError } from '../../api/client';
import type { Agent } from '../../api/types';

const chatStore = useChatStore();

const agents = ref<Agent[]>([]);
const loading = ref(false);
const pageError = ref('');
const createVisible = ref(false);
const creating = ref(false);
const form = ref({ display_name: '', handle: '', bio: '' });

onShow(async () => {
  await load(chatStore.agentsStale);
  chatStore.agentsStale = false;
});

async function load(showToastOnFail = false) {
  loading.value = true;
  pageError.value = '';
  try {
    const res = await agentsApi.listAgents('owned');
    agents.value = res.items ?? [];
  } catch (e) {
    pageError.value = describeError(e);
  } finally {
    loading.value = false;
  }
}

function statusText(status: string): string {
  if (status === 'active') return '正常';
  if (status === 'disabled') return '已停用';
  return status;
}

function bindingLine(a: Agent): string {
  const b = a.binding;
  if (!b) return '未绑定运行方式';
  if (b.mode === 'model_api') {
    const model = [b.provider_code, b.model_name].filter(Boolean).join('/');
    return `模型 API · ${model || '已配置'}${b.enabled ? '' : '（未启用）'}`;
  }
  return `连接器 · 代际 ${b.generation}${b.enabled ? '' : '（未启用）'}`;
}

function openDetail(a: Agent) {
  uni.navigateTo({ url: `/pages/agents/detail?id=${a.agent_id}` });
}

async function create() {
  if (creating.value) return;
  const displayName = form.value.display_name.trim();
  const handle = form.value.handle.trim();
  if (!displayName || !handle) {
    uni.showToast({ title: '请填写名称与账号名', icon: 'none' });
    return;
  }
  creating.value = true;
  try {
    await agentsApi.createAgent({ display_name: displayName, handle, bio: form.value.bio.trim() || undefined });
    uni.showToast({ title: '已创建（未绑定）', icon: 'none' });
    form.value = { display_name: '', handle: '', bio: '' };
    createVisible.value = false;
    await load();
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  } finally {
    creating.value = false;
  }
}
</script>
<style scoped>.ai-intro { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 32px; margin-bottom: 26px; border: 1px solid #c7d7be; border-radius: 26px; background: radial-gradient(circle at 90% 30%,#d9d0f0,transparent 30%),#eaf4df; }.ai-intro-title { display: block; font-size: 30px; line-height: 1.3; font-weight: 820; letter-spacing: -.035em; color: #102a22; }.ai-intro-description { display: block; margin-top: 13px; font-size: 12px; line-height: 1.7; color: var(--text-secondary); }.ai-intro-art { position: relative; flex: 0 0 90px; width: 90px; height: 90px; display: flex; align-items: center; justify-content: center; border: 1px solid #9caf96; border-radius: 28px; background: var(--surface); box-shadow: 7px 7px 0 #b5c9aa; animation: ui-float 5s infinite; transform: rotate(-8deg); }.art-spark { position: absolute; top: -12px; right: -12px; display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; border: 1px solid #ae99cc; border-radius: 12px; background: #cdb8f0; }.agent-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(min(100%,270px),1fr)); gap: 18px; }.agent-card { display: flex; flex-direction: column; margin: 0; padding: 24px; min-width: 0; border: 1px solid var(--line); border-radius: 22px; background: var(--surface); color: var(--text); text-align: left; line-height: 1.5; transition: transform 180ms,box-shadow 180ms; }.agent-card::after { display: none; }.agent-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-card); }.agent-card-top { display: flex; align-items: center; justify-content: space-between; width: 100%; }.agent-name { display: block; margin-top: 20px; font-size: 20px; font-weight: 760; }.agent-handle { font-size: 11px; color: var(--text-secondary); margin-top: 3px; }.agent-bio { display: block; flex: 1; margin: 16px 0 22px; font-size: 13px; color: var(--text-secondary); line-height: 1.7; }.agent-binding { display: flex; align-items: center; gap: 8px; width: 100%; padding-top: 16px; border-top: 1px solid var(--line); font-size: 11px; color: var(--text-secondary); }.agent-binding > text { flex: 1; min-width: 0; overflow-wrap: anywhere; }.create-form { padding: 0 22px 22px; }@media(max-width:767px){.ai-intro { padding: 24px; }.ai-intro-title { font-size: 24px; }.ai-intro-art { flex-basis: 64px; width: 64px; height: 64px; border-radius: 20px; }}@media(max-width:380px){.ai-intro-art { display: none; }}</style>
