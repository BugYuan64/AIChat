<script setup lang="ts">
import { computed } from 'vue';
import UiIcon from './UiIcon.vue';

const props = withDefaults(defineProps<{
  name?: string;
  kind?: 'human' | 'agent' | 'group';
  size?: 'small' | 'medium' | 'large';
  online?: boolean;
}>(), { name: '', kind: 'human', size: 'medium', online: false });

const initials = computed(() => props.name.trim().slice(0, 2).toUpperCase() || 'AI');
</script>

<template>
  <view class="account-avatar" :class="[`account-avatar--${kind}`, `account-avatar--${size}`]" :aria-label="name || kind">
    <UiIcon v-if="kind === 'agent'" name="bot" tone="primary" :size="size === 'large' ? 28 : 20" />
    <UiIcon v-else-if="kind === 'group'" name="users" tone="primary" :size="size === 'large' ? 28 : 20" />
    <text v-else>{{ initials }}</text>
    <view v-if="online" class="account-avatar__presence" aria-label="在线" />
  </view>
</template>

<style scoped lang="scss">
.account-avatar { position: relative; width: 46px; height: 46px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; border: 1px solid var(--line); border-radius: 16px; background: var(--surface-elevated); color: var(--text-secondary); font-size: 14px; font-weight: 760; box-sizing: border-box; }
.account-avatar--small { width: 34px; height: 34px; border-radius: 12px; font-size: 12px; }
.account-avatar--large { width: 64px; height: 64px; border-radius: 20px; font-size: 20px; }
.account-avatar--agent { background: var(--accent-soft); border-color: rgba(25, 107, 85, 0.12); }
.account-avatar--group { background: var(--violet-soft); border-color: rgba(125, 91, 198, 0.14); }
.account-avatar__presence { position: absolute; right: -1px; bottom: -1px; width: 11px; height: 11px; border: 2px solid var(--surface); border-radius: 50%; background: var(--success); box-sizing: border-box; }
</style>
