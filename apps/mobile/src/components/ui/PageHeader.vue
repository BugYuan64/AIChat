<script setup lang="ts">
import UiButton from './UiButton.vue';
import type { UiIconName } from '../../ui/icons';
import { goBack, type BackFallback } from '../../utils/nav';

const props = withDefaults(defineProps<{
  title: string;
  eyebrow?: string;
  subtitle?: string;
  back?: boolean;
  /** 页面栈只有一层时的兜底去向；默认回到会话列表 */
  backFallback?: BackFallback;
  actionIcon?: UiIconName;
  actionLabel?: string;
  sticky?: boolean;
}>(), {
  eyebrow: '',
  subtitle: '',
  back: false,
  backFallback: () => ({ url: '/pages/sessions/sessions', tab: true }),
  actionIcon: undefined,
  actionLabel: '',
  sticky: false,
});

const emit = defineEmits<{ back: []; action: [] }>();
function handleBack() {
  emit('back');
  if (!props.back) return;
  goBack(props.backFallback);
}
</script>

<template>
  <view class="page-header" :class="{ 'page-header--sticky': sticky }">
    <UiButton v-if="back" class="page-header__control" variant="ghost" size="icon" icon="arrow-left" label="返回" @click="handleBack" />
    <view class="page-header__copy">
      <text v-if="eyebrow" class="page-header__eyebrow">{{ eyebrow }}</text>
      <text class="page-header__title">{{ title }}</text>
      <text v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</text>
    </view>
    <slot name="actions">
      <UiButton v-if="actionIcon" class="page-header__control" variant="ghost" size="icon" :icon="actionIcon" :label="actionLabel" @click="emit('action')" />
    </slot>
  </view>
</template>

<style scoped lang="scss">
.page-header { min-height: 72px; display: flex; align-items: center; gap: 8px; padding: 14px var(--page-gutter); box-sizing: border-box; }
.page-header--sticky { position: sticky; top: 0; z-index: 20; background: color-mix(in srgb, var(--canvas) 88%, transparent); backdrop-filter: blur(18px); }
.page-header__copy { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.page-header__eyebrow { color: var(--accent); font-size: 12px; font-weight: 750; letter-spacing: 0.08em; text-transform: uppercase; }
.page-header__title { color: var(--text); font-size: 23px; font-weight: 760; line-height: 1.22; letter-spacing: -0.02em; }
.page-header__subtitle { margin-top: 3px; color: var(--text-secondary); font-size: 13px; line-height: 1.45; }
.page-header__control { flex: 0 0 auto; }
</style>
