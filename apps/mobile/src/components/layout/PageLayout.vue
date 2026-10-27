<script setup lang="ts">
import AppShell from './AppShell.vue';
import PageHeader from '../ui/PageHeader.vue';
import { useAuthStore } from '../../stores/auth';
import type { BackFallback } from '../../utils/nav';
const auth = useAuthStore();
withDefaults(defineProps<{ title: string; eyebrow?: string; subtitle?: string; active?: 'sessions' | 'contacts' | 'agents' | 'me'; back?: boolean; backFallback?: BackFallback }>(), { eyebrow: '', subtitle: '', active: 'me', back: false });
</script>
<template>
  <AppShell :active="active" :display-name="auth.account?.display_name || auth.account?.handle || 'AIChat'"><view class="page-layout"><PageHeader :title="title" :eyebrow="eyebrow" :subtitle="subtitle" :back="back" :back-fallback="backFallback"><template #actions><slot name="actions" /></template></PageHeader><view class="page-layout__content motion-enter"><slot /></view></view><template #overlay><slot name="overlay" /></template></AppShell>
</template>
<style scoped>
.page-layout { max-width: 1140px; margin: 0 auto; }.page-layout__content { padding: 8px var(--page-gutter) 36px; }.page-layout :deep(.page-header) { padding-top: 24px; padding-bottom: 24px; }
</style>
