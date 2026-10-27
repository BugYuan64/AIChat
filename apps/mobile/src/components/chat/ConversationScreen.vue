<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useAuthStore } from '../../stores/auth';
import { useChatStore } from '../../stores/chat';
import { describeError } from '../../api/client';
import AppShell from '../layout/AppShell.vue';
import ConversationList from './ConversationList.vue';
import ChatWorkspace from './ChatWorkspace.vue';
import UiIcon from '../ui/UiIcon.vue';
import UiButton from '../ui/UiButton.vue';
import type { ConversationItem } from '../../api/types';
const props = withDefaults(defineProps<{ id?: string; active?: boolean }>(), { id: '', active: true });
const auth = useAuthStore();
const chat = useChatStore();
const loading = ref(false);
const error = ref('');
const name = computed(() => auth.account?.display_name || auth.account?.handle || 'AIChat');
watch(() => props.active, (value) => { if (value) void refresh(); }, { immediate: true });
async function refresh() {
  if (!auth.isLoggedIn) { uni.reLaunch({ url: '/pages/login/login' }); return; }
  loading.value = true;
  error.value = '';
  try { await chat.loadConversations(); }
  catch (e) { error.value = describeError(e); }
  finally { loading.value = false; }
}
function select(item: ConversationItem) {
  if (item.conversation_id === props.id) return;
  const url = '/pages/chat/chat?id=' + encodeURIComponent(item.conversation_id);
  if (props.id) uni.redirectTo({ url }); else uni.navigateTo({ url });
}
function create() {
  uni.showActionSheet({ itemList: ['发起私聊', '创建群聊'], success: (result) => {
    chat.requestGroupCreate = result.tapIndex === 1;
    uni.switchTab({ url: '/pages/contacts/contacts' });
  } });
}
function openAgents() { uni.navigateTo({ url: '/pages/agents/agents' }); }
</script>
<template>
  <AppShell active="sessions" :display-name="name" :contained="false">
    <view class="conversation-screen" :class="{ 'has-conversation': id }">
      <view class="conversation-sidebar"><ConversationList :items="chat.sortedConversations" :active-id="id" :loading="loading" :error="error" @select="select" @create="create" @retry="refresh" /></view>
      <view class="conversation-workspace">
        <ChatWorkspace v-if="id" :key="id" :id="id" :active="active" />
        <view v-else class="workspace-welcome">
          <view class="welcome-art"><view class="welcome-orbit" /><UiIcon name="sparkles" tone="primary" :size="40" /></view>
          <text class="welcome-eyebrow">MAKE ROOM FOR IDEAS</text>
          <text class="welcome-title">从一个想法，<br />到一起完成。</text>
          <text class="welcome-description">选择一段对话，连接你的团队与 AI 搭档。<br />好的协作，从把事情聊清楚开始。</text>
          <view class="welcome-actions"><UiButton icon="message-square-plus" @click="create">开始新对话</UiButton><UiButton variant="secondary" icon="bot" @click="openAgents">管理我的 AI</UiButton></view>
          <view class="welcome-note"><UiIcon name="shield-check" tone="muted" :size="14" /><text>人类与 AI，各有身份，共享空间。</text></view>
        </view>
      </view>
    </view>
  </AppShell>
</template>
<style scoped>
.conversation-screen { display: flex; height: calc(100vh - var(--window-bottom, 0px)); height: calc(100dvh - var(--window-bottom, 0px)); min-width: 0; }.conversation-sidebar { width: 100%; flex: 0 0 100%; min-width: 0; border-right: 1px solid var(--line); }.conversation-workspace { display: none; flex: 1; min-width: 0; height: 100%; }.has-conversation .conversation-sidebar { display: none; }.has-conversation .conversation-workspace { display: block; }.workspace-welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 30px; text-align: center; background: radial-gradient(ellipse at 20% 0%, var(--accent-soft), transparent 55%), var(--canvas); }.welcome-art { position: relative; width: 92px; height: 92px; display: flex; align-items: center; justify-content: center; margin-bottom: 32px; border: 1px solid #bad3bb; border-radius: 30px; background: #e8f2df; transform: rotate(-8deg); animation: ui-float 5s ease-in-out infinite; }.welcome-orbit { position: absolute; width: 105px; height: 105px; border: 1px dashed #bda8df; border-radius: 34px; transform: rotate(20deg); }.welcome-eyebrow { color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: .14em; }.welcome-title { margin-top: 14px; font-size: clamp(28px,3vw,44px); color: var(--text); font-weight: 820; line-height: 1.3; letter-spacing: -.04em; }.welcome-description { margin-top: 18px; font-size: 13px; line-height: 1.9; color: var(--text-secondary); }.welcome-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 28px; }.welcome-note { display: flex; align-items: center; gap: 6px; margin-top: 50px; font-size: 11px; color: var(--text-secondary); }
@media (min-width: 900px) { .conversation-screen { height: 100vh; height: 100dvh; }.conversation-sidebar, .has-conversation .conversation-sidebar { display: block; width: 310px; flex: 0 0 310px; }.conversation-workspace { display: block; } }
@media (min-width: 1100px) { .conversation-sidebar, .has-conversation .conversation-sidebar { width: 330px; flex-basis: 330px; } }
</style>
