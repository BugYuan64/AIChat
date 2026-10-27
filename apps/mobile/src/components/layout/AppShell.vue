<script setup lang="ts">
import DesktopRail from './DesktopRail.vue';

withDefaults(defineProps<{
  active?: 'sessions' | 'contacts' | 'agents' | 'me';
  displayName?: string;
  contained?: boolean;
}>(), { active: 'sessions', displayName: 'AIChat', contained: true });
</script>

<template>
  <view class="app-shell">
    <DesktopRail :active="active" :display-name="displayName" />
    <view class="app-shell__main" :class="{ 'app-shell__main--contained': contained }">
      <slot />
    </view>
    <slot name="overlay" />
  </view>
</template>

<style scoped lang="scss">
.app-shell { min-height: calc(100vh - var(--window-bottom, 0px)); display: flex; background: var(--canvas); }
.app-shell__main { width: 100%; min-width: 0; box-sizing: border-box; }
@media (min-width: 768px) { .app-shell__main--contained { padding: 18px; } }
@media (min-width: 900px) { .app-shell__main { flex: 1; } .app-shell__main--contained { padding: 22px; } }
</style>
