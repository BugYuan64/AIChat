<script setup lang="ts">
import UiButton from './UiButton.vue';
import UiIcon from './UiIcon.vue';
import type { UiIconName } from '../../ui/icons';

withDefaults(defineProps<{
  icon?: UiIconName;
  title: string;
  description?: string;
  actionLabel?: string;
}>(), { icon: 'sparkles', description: '', actionLabel: '' });
const emit = defineEmits<{ action: [] }>();
</script>

<template>
  <view class="empty-state">
    <view class="empty-state__art"><UiIcon :name="icon" tone="primary" :size="28" /></view>
    <text class="empty-state__title">{{ title }}</text>
    <text v-if="description" class="empty-state__description">{{ description }}</text>
    <UiButton v-if="actionLabel" class="empty-state__action" variant="secondary" size="small" @click="emit('action')">{{ actionLabel }}</UiButton>
  </view>
</template>

<style scoped lang="scss">
.empty-state { min-height: 240px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 36px 24px; text-align: center; animation: ui-rise var(--motion-slow) var(--ease-out) both; box-sizing: border-box; }
.empty-state__art { width: 58px; height: 58px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; border: 1px solid rgba(25, 107, 85, 0.14); border-radius: 20px; background: var(--accent-soft); box-shadow: var(--shadow-soft); }
.empty-state__title { color: var(--text); font-size: 17px; font-weight: 740; }
.empty-state__description { max-width: 340px; margin-top: 7px; color: var(--text-secondary); font-size: 13px; line-height: 1.65; }
.empty-state__action { margin-top: 18px; }
</style>
