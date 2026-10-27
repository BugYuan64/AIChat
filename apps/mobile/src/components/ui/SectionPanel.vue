<script setup lang="ts">
import UiIcon from './UiIcon.vue';
import type { UiIconName } from '../../ui/icons';
withDefaults(defineProps<{ title?: string; description?: string; icon?: UiIconName; tone?: 'default' | 'mint' | 'violet' | 'danger' }>(), { title: '', description: '', icon: undefined, tone: 'default' });
</script>
<template><view class="section-panel" :class="'section-panel--' + tone"><view v-if="title" class="panel-heading"><view v-if="icon" class="panel-icon"><UiIcon :name="icon" :tone="tone === 'danger' ? 'danger' : 'primary'" :size="20" /></view><view class="panel-copy"><text class="panel-title">{{ title }}</text><text v-if="description" class="panel-description">{{ description }}</text></view><slot name="action" /></view><slot /></view></template>
<style scoped>
.section-panel { min-width: 0; padding: 24px; border: 1px solid var(--line); border-radius: var(--radius-card); background: var(--surface); box-shadow: 0 4px 22px rgba(25,45,34,.035); }.section-panel--mint { background: #eaf3e5; border-color: #c6d7bf; }.section-panel--violet { background: #f0ecf8; border-color: #d8cbed; }.section-panel--danger { background: #fcf4f1; border-color: #ecd4cf; }.panel-heading { display: flex; align-items: center; gap: 11px; margin-bottom: 22px; }.panel-copy { flex: 1; min-width: 0; }.panel-icon { width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; border-radius: 13px; background: var(--accent-soft); }.panel-title { display: block; color: var(--text); font-size: 16px; font-weight: 760; }.panel-description { display: block; margin-top: 4px; color: var(--text-secondary); font-size: 12px; line-height: 1.6; }@media(max-width:380px){.section-panel { padding: 18px; }}
</style>
