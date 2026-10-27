<script setup lang="ts">
import UiIcon from './UiIcon.vue';
import type { UiIconName } from '../../ui/icons';

withDefaults(defineProps<{
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'violet';
  icon?: UiIconName;
  pulse?: boolean;
}>(), { tone: 'neutral', icon: undefined, pulse: false });
</script>

<template>
  <view class="status-badge" :class="[`status-badge--${tone}`, { 'status-badge--pulse': pulse }]">
    <UiIcon v-if="icon" :name="icon" :tone="tone === 'danger' ? 'danger' : tone === 'success' || tone === 'primary' ? 'primary' : 'muted'" :size="13" />
    <text><slot /></text>
  </view>
</template>

<style scoped lang="scss">
.status-badge { display: inline-flex; align-items: center; gap: 5px; min-height: 24px; padding: 0 9px; border-radius: 999px; background: var(--surface-soft); color: var(--text-secondary); font-size: 11px; font-weight: 720; line-height: 1; white-space: nowrap; }
.status-badge--primary, .status-badge--success { background: var(--accent-soft); color: var(--accent); }
.status-badge--warning { background: var(--warning-soft); color: var(--warning); }
.status-badge--danger { background: var(--danger-soft); color: var(--danger); }
.status-badge--violet { background: var(--violet-soft); color: var(--violet); }
.status-badge--pulse::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: ui-pulse 1.8s ease-in-out infinite; }
</style>
