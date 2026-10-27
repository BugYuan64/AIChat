<script setup lang="ts">
import { computed, ref } from 'vue';
import type { ConversationItem } from '../../api/types';
import { filterConversations } from '../../ui/chat';
import { formatTime } from '../../utils/misc';
import AccountAvatar from '../ui/AccountAvatar.vue';
import UiButton from '../ui/UiButton.vue';
import UiIcon from '../ui/UiIcon.vue';
import EmptyState from '../ui/EmptyState.vue';
import InlineNotice from '../ui/InlineNotice.vue';
import NativeButton from '../ui/NativeButton.vue';
const props = withDefaults(defineProps<{ items: ConversationItem[]; activeId?: string; loading?: boolean; error?: string }>(), { activeId: '', loading: false, error: '' });
const emit = defineEmits<{ select: [item: ConversationItem]; create: []; retry: [] }>();
const query = ref('');
const filtered = computed(() => filterConversations(props.items, query.value));
</script>
<template>
  <view class="conversation-list">
    <view class="conversation-head"><view><text class="overline">YOUR WORKSPACE</text><text class="conversation-title">会话<text class="conversation-count">{{ items.length }}</text></text></view><UiButton size="icon" icon="square-pen" label="新建会话" @click="emit('create')" /></view>
    <view class="conversation-search"><UiIcon name="search" tone="muted" :size="18" /><input v-model="query" aria-label="搜索会话" placeholder="搜索会话或账号" /></view>
    <view class="conversation-caption"><text>最近对话</text><text>{{ filtered.length }} 个</text></view>
    <InlineNotice v-if="error" tone="danger">{{ error }}<UiButton variant="ghost" size="small" @click="emit('retry')">重试</UiButton></InlineNotice>
    <view v-if="loading && !items.length" class="conversation-loading"><view v-for="i in 4" :key="i" class="skeleton" /></view>
    <scroll-view v-else class="conversation-scroll" scroll-y>
      <NativeButton v-for="item in filtered" :key="item.conversation_id" class="conversation-row" :class="{ selected: activeId === item.conversation_id }" @click="emit('select', item)">
        <AccountAvatar :name="item.title" :kind="item.kind === 'group' ? 'group' : item.direct_peer?.kind === 'ai' ? 'agent' : 'human'" />
        <view class="conversation-body"><view class="conversation-line"><text class="conversation-name">{{ item.title || item.direct_peer?.display_name || '会话' }}</text><text v-if="item.direct_peer?.kind === 'ai'" class="conversation-ai">AI</text></view><text class="conversation-preview">{{ item.closed ? '会话已关闭' : item.last_message?.text || '发一条消息，开始对话' }}</text></view>
        <view class="conversation-end"><text>{{ formatTime(item.last_message?.created_at || item.updated_at) }}</text><text v-if="item.unread_count" class="conversation-unread">{{ item.unread_count > 99 ? '99+' : item.unread_count }}</text></view>
      </NativeButton>
      <EmptyState v-if="!filtered.length" icon="message-circle" :title="query ? '没有匹配的会话' : '从一段对话开始'" :description="query ? '试试其他关键词' : '添加联系人，或创建一个属于团队的群聊。'" :action-label="query ? '' : '新建会话'" @action="emit('create')" />
    </scroll-view>
  </view>
</template>
<style scoped>
.conversation-list { display: flex; flex-direction: column; height: 100%; min-width: 0; background: var(--surface); }.conversation-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 26px 20px 20px; }.overline { display: block; color: var(--accent); font-size: 9px; font-weight: 800; letter-spacing: .12em; }.conversation-title { display: block; margin-top: 4px; font-size: 25px; font-weight: 800; letter-spacing: -.04em; }.conversation-count { margin-left: 9px; font-size: 12px; color: var(--text-secondary); font-weight: 600; }.conversation-search { display: flex; align-items: center; gap: 9px; padding: 0 12px; margin: 0 16px; height: 44px; border: 1px solid var(--line); border-radius: 13px; background: var(--surface-soft); }.conversation-search input { flex: 1; min-width: 0; font-size: 13px; }.conversation-caption { display: flex; justify-content: space-between; margin: 22px 20px 8px; color: var(--text-secondary); font-size: 11px; }.conversation-scroll { flex: 1; height: 0; }.conversation-row { display: flex; align-items: center; gap: 11px; width: calc(100% - 16px); min-height: 88px; margin: 3px 8px; padding: 14px 12px; border: 1px solid transparent; border-radius: 16px; background: transparent; color: var(--text); text-align: left; line-height: 1.4; transition: background var(--motion-fast), transform var(--motion-fast); }.conversation-row::after { display: none; }.conversation-row:hover { background: var(--surface-soft); transform: translateX(2px); }.conversation-row.selected { background: var(--accent-soft); border-color: #c9dfce; }.conversation-body { flex: 1; min-width: 0; }.conversation-line { display: flex; align-items: center; gap: 6px; }.conversation-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 720; }.conversation-ai { font-size: 9px; color: var(--violet); background: var(--violet-soft); padding: 1px 5px; border-radius: 5px; }.conversation-preview { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary); font-size: 12px; margin-top: 5px; }.conversation-end { align-self: stretch; display: flex; flex-direction: column; align-items: flex-end; gap: 9px; color: var(--text-secondary); font-size: 10px; }.conversation-unread { min-width: 19px; padding: 2px 5px; border-radius: 20px; background: var(--accent); color: white; text-align: center; font-size: 10px; }.conversation-loading { padding: 20px; }.conversation-loading .skeleton { height: 62px; margin-bottom: 16px; }
</style>
