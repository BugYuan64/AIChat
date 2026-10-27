<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue';
import UiButton from './UiButton.vue';

const props = withDefaults(defineProps<{ open: boolean; title?: string; closeLabel?: string }>(), { title: '', closeLabel: '关闭' });
const emit = defineEmits<{ close: [] }>();
const mask = ref<{ $el?: HTMLElement } | HTMLElement | null>(null);
// #ifdef H5
let previousFocus: HTMLElement | null = null;
function element(): HTMLElement | null { const target = mask.value; return target ? ('$el' in target ? target.$el || null : target as HTMLElement) : null; }
function keydown(event: KeyboardEvent) {
  if (!props.open) return;
  if (event.key === 'Escape') { event.preventDefault(); emit('close'); return; }
  if (event.key !== 'Tab') return;
  const buttons = Array.from(element()?.querySelectorAll<HTMLElement>('button:not([disabled]), input, textarea, [tabindex="0"]') || []).filter((item) => item.offsetParent !== null);
  const first = buttons[0], last = buttons[buttons.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
}
watch(() => props.open, async (open) => {
  if (open) { previousFocus = document.activeElement as HTMLElement; document.addEventListener('keydown', keydown); await nextTick(); element()?.querySelector<HTMLElement>('button, input')?.focus(); }
  else { document.removeEventListener('keydown', keydown); previousFocus?.focus(); }
}, { immediate: true });
onUnmounted(() => document.removeEventListener('keydown', keydown));
// #endif
</script>

<template>
  <view v-if="open" ref="mask" class="bottom-sheet__mask" role="presentation" @tap.self="emit('close')">
    <view class="bottom-sheet" role="dialog" aria-modal="true" :aria-label="title || '操作面板'">
      <view class="bottom-sheet__handle" />
      <view class="bottom-sheet__header">
        <text class="bottom-sheet__title">{{ title }}</text>
        <UiButton variant="ghost" size="icon" icon="x" :label="closeLabel" @click="emit('close')" />
      </view>
      <scroll-view class="bottom-sheet__content" scroll-y><slot /></scroll-view>
      <view v-if="$slots.footer" class="bottom-sheet__footer"><slot name="footer" /></view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.bottom-sheet__mask { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: flex-end; justify-content: center; background: var(--scrim); animation: ui-fade var(--motion-normal) var(--ease-out) both; }
.bottom-sheet { width: min(100%, 620px); max-height: min(78vh, 720px); padding-bottom: env(safe-area-inset-bottom); border: 1px solid var(--line); border-bottom: 0; border-radius: 28px 28px 0 0; background: var(--surface); box-shadow: var(--shadow-float); animation: ui-sheet var(--motion-slow) var(--ease-spring) both; overflow: hidden; }
.bottom-sheet__handle { width: 42px; height: 4px; margin: 10px auto 2px; border-radius: 999px; background: var(--line-strong); }
.bottom-sheet__header { min-height: 58px; display: flex; align-items: center; gap: 12px; padding: 6px 12px 6px 20px; }
.bottom-sheet__title { flex: 1; color: var(--text); font-size: 18px; font-weight: 740; }
.bottom-sheet__content { max-height: 54vh; box-sizing: border-box; }
.bottom-sheet__footer { padding: 14px 18px; border-top: 1px solid var(--line); }
</style>
