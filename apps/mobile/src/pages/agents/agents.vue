<template>
  <view class="page">
    <view v-if="!agents.length && !loading" class="empty">
      还没有创建 AI
      <view class="empty-sub">点击下方「创建 AI」建立第一个 AI 账号，再绑定模型或连接器</view>
    </view>

    <view v-for="a in agents" :key="a.agent_id" class="list-item" @tap="openDetail(a)">
      <view class="avatar ai">{{ (a.display_name || 'A').slice(0, 1).toUpperCase() }}</view>
      <view class="list-body">
        <view class="row-line">
          <text class="list-title">{{ a.display_name }}</text>
          <text class="tag tag-ai">AI</text>
          <text :class="['tag', a.online ? 'tag-online' : 'tag-offline']">{{ a.online ? '在线' : '离线' }}</text>
        </view>
        <view class="list-sub">@{{ a.handle }} · {{ statusText(a.status) }}</view>
        <view class="list-sub binding">{{ bindingLine(a) }}</view>
      </view>
      <view class="list-end"><text class="arrow">›</text></view>
    </view>

    <view class="card">
      <view v-if="!createVisible" class="btn btn-primary" @tap="createVisible = true">创建 AI</view>
      <view v-else>
        <view class="field">
          <view class="field-label">AI 名称</view>
          <input v-model="form.display_name" class="input" placeholder="例如：代码助手" :maxlength="64" />
        </view>
        <view class="field">
          <view class="field-label">账号名（handle）</view>
          <input v-model="form.handle" class="input" placeholder="唯一，不可重复" :maxlength="64" />
        </view>
        <view class="field">
          <view class="field-label">简介（可选）</view>
          <textarea v-model="form.bio" class="textarea" placeholder="这个 AI 的定位" :maxlength="500" />
        </view>
        <view class="btn btn-primary" :class="{ 'btn-disabled': creating }" @tap="create">
          {{ creating ? '创建中…' : '确认创建' }}
        </view>
        <view class="btn" @tap="createVisible = false">取消</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import * as agentsApi from '../../api/agents';
import { useChatStore } from '../../stores/chat';
import { describeError } from '../../api/client';
import type { Agent } from '../../api/types';

const chatStore = useChatStore();

const agents = ref<Agent[]>([]);
const loading = ref(false);
const createVisible = ref(false);
const creating = ref(false);
const form = ref({ display_name: '', handle: '', bio: '' });

onShow(async () => {
  await load(chatStore.agentsStale);
  chatStore.agentsStale = false;
});

async function load(showToastOnFail = false) {
  loading.value = true;
  try {
    const res = await agentsApi.listAgents('owned');
    agents.value = res.items ?? [];
  } catch (e) {
    if (showToastOnFail) uni.showToast({ title: describeError(e), icon: 'none' });
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

<style lang="scss" scoped>
.row-line {
  display: flex;
  align-items: center;
}
.binding {
  color: #5b6472;
}
.empty-sub {
  font-size: 22rpx;
  color: #b6bcc4;
  margin-top: 12rpx;
}
.arrow {
  color: #c2c8d0;
  font-size: 36rpx;
}
</style>
