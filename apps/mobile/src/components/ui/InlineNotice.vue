<script setup lang="ts">
import { computed } from 'vue';
import UiIcon from './UiIcon.vue';

const props = withDefaults(defineProps<{
  tone?: 'info' | 'success' | 'warning' | 'danger';
  title?: string;
  dismissible?: boolean;
}>(), { tone: 'info', title: '', dismissible: false });
const emit = defineEmits<{ dismiss: [] }>();
const icon = computed(() => ({ info: 'info', success: 'circle-check', warning: 'triangle-alert', danger: 'circle-alert' } as const)[props.tone]);
</script>

<template>
  <view class="inline-notice" :class="`inline-notice--${tone}`" role="status">
    <UiIcon :name="icon" :tone="tone === 'danger' ? 'danger' : tone === 'success' ? 'primary' : 'muted'" :size="18" />
    <view class="inline-notice__body">
      <text v-if="title" class="inline-notice__title">{{ title }}</text>
      <text class="inline-notice__message"><slot /></text>
    </view>
    <button v-if="dismissible" class="inline-notice__close" type="button" aria-label="关闭提示" @click="emit('dismiss')">
      <UiIcon name="x" tone="muted" :size="16" />
    </button>
  </view>
</template>

<style scoped lang="scss">
.inline-notice { display: flex; align-items: flex-start; gap: 10px; padding: 13px 14px; border: 1px solid var(--line); border-radius: var(--radius-control); background: var(--surface-soft); color: var(--text-secondary); }
.inline-notice--info { background: var(--info-soft); border-color: rgba(67, 102, 140, 0.16); }
.inline-notice--success { background: var(--accent-soft); border-color: rgba(25, 107, 85, 0.14); }
.inline-notice--warning { background: var(--warning-soft); border-color: rgba(145, 94, 19, 0.14); }
.inline-notice--danger { background: var(--danger-soft); border-color: rgba(178, 59, 56, 0.14); }
.inline-notice__body { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.inline-notice__title { margin-bottom: 3px; color: var(--text); font-size: 13px; font-weight: 740; }
.inline-notice__message { font-size: 12px; line-height: 1.55; }
.inline-notice__close { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; margin: -5px -6px 0 0; padding: 0; border: 0; border-radius: 9px; background: transparent; }
.inline-notice__close::after { display: none; }
</style>
