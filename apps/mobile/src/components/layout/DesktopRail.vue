<script setup lang="ts">
import AccountAvatar from '../ui/AccountAvatar.vue';
import UiButton from '../ui/UiButton.vue';
import UiIcon from '../ui/UiIcon.vue';
import NativeButton from '../ui/NativeButton.vue';
import type { UiIconName } from '../../ui/icons';

type RailKey = 'sessions' | 'contacts' | 'agents' | 'me';
const props = withDefaults(defineProps<{ active?: RailKey; displayName?: string }>(), { active: 'sessions', displayName: 'AIChat' });
const emit = defineEmits<{ navigate: [key: RailKey] }>();
const items: { key: RailKey; label: string; icon: UiIconName; url: string; tab: boolean }[] = [
  { key: 'sessions', label: '会话', icon: 'message-circle', url: '/pages/sessions/sessions', tab: true },
  { key: 'contacts', label: '联系人', icon: 'users', url: '/pages/contacts/contacts', tab: true },
  { key: 'agents', label: '我的 AI', icon: 'bot', url: '/pages/agents/agents', tab: false },
  { key: 'me', label: '我的', icon: 'user-round', url: '/pages/me/me', tab: true },
];

function navigate(item: (typeof items)[number]) {
  emit('navigate', item.key);
  if (getCurrentPages().at(-1)?.route === item.url.slice(1)) return;
  if (item.tab) uni.switchTab({ url: item.url });
  else uni.navigateTo({ url: item.url });
}
</script>

<template>
  <view class="desktop-rail">
    <view class="desktop-rail__brand" aria-label="AIChat 首页">
      <view class="desktop-rail__mark"><UiIcon name="sparkles" tone="inverse" :size="20" /></view>
      <text>AIChat</text>
    </view>
    <view class="desktop-rail__nav">
      <NativeButton v-for="item in items" :key="item.key" type="button" class="desktop-rail__item" :class="{ active: item.key === active }" :aria-label="item.label" @click="navigate(item)">
        <UiIcon :name="item.icon" :tone="item.key === active ? 'primary' : 'muted'" :size="20" />
        <text>{{ item.label }}</text>
      </NativeButton>
    </view>
    <view class="desktop-rail__footer">
      <AccountAvatar :name="displayName" size="small" />
      <text class="desktop-rail__name">{{ displayName }}</text>
      <UiButton variant="ghost" size="icon" icon="settings-2" label="设置" @click="navigate(items[3])" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.desktop-rail { width: 232px; min-height: 100vh; display: none; flex-direction: column; padding: 18px 14px; border-right: 1px solid var(--line); background: var(--surface); box-sizing: border-box; }
.desktop-rail__brand { height: 54px; display: flex; align-items: center; gap: 10px; padding: 0 10px; color: var(--text); font-size: 18px; font-weight: 800; letter-spacing: -0.02em; }
.desktop-rail__mark { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 12px; background: var(--accent); box-shadow: 0 8px 18px rgba(25, 107, 85, 0.2); }
.desktop-rail__nav { flex: 1; display: flex; flex-direction: column; gap: 5px; margin-top: 24px; }
.desktop-rail__item { min-height: 46px; display: flex; align-items: center; gap: 11px; margin: 0; padding: 0 12px; border: 0; border-radius: 14px; background: transparent; color: var(--text-secondary); font-size: 14px; font-weight: 620; text-align: left; transition: background var(--motion-fast) var(--ease-out), transform var(--motion-fast) var(--ease-out); }
.desktop-rail__item::after { display: none; }
.desktop-rail__item:hover { background: var(--surface-soft); transform: translateX(2px); }
.desktop-rail__item.active { background: var(--accent-soft); color: var(--accent); }
.desktop-rail__footer { display: flex; align-items: center; gap: 10px; padding: 12px 4px 0; border-top: 1px solid var(--line); }
.desktop-rail__name { flex: 1; min-width: 0; overflow: hidden; color: var(--text); font-size: 13px; font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
@media (min-width: 900px) { .desktop-rail { display: flex; } }
@media (min-width: 900px) and (max-width: 1099px) { .desktop-rail { width: 76px; padding: 18px 8px; }.desktop-rail__brand { padding: 0; justify-content: center; }.desktop-rail__brand > text, .desktop-rail__item > text, .desktop-rail__name, .desktop-rail__footer > .ui-button { display: none; }.desktop-rail__item { justify-content: center; padding: 0; }.desktop-rail__footer { justify-content: center; } }
</style>
