<script setup lang="ts">
import { ref } from 'vue';
import { onShow, onHide } from '@dcloudio/uni-app';
import ConversationScreen from '../../components/chat/ConversationScreen.vue';
const active = ref(true);
onShow(() => { active.value = true; });
onHide(() => { active.value = false; });
</script>
<template><ConversationScreen :active="active" /></template>
