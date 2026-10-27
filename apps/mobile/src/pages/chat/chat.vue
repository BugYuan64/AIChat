<script setup lang="ts">
import { ref } from 'vue';
import { onLoad, onShow, onHide } from '@dcloudio/uni-app';
import ConversationScreen from '../../components/chat/ConversationScreen.vue';
const id = ref('');
const active = ref(true);
onLoad((options) => { id.value = options?.id || ''; if (!id.value) uni.switchTab({ url: '/pages/sessions/sessions' }); });
onShow(() => { active.value = true; });
onHide(() => { active.value = false; });
</script>
<template><ConversationScreen v-if="id" :id="id" :active="active" /></template>
