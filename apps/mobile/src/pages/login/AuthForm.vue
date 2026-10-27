<script setup lang="ts">
const emit = defineEmits<{ submit: [] }>();
</script>
<template>
  <!-- #ifdef H5 -->
  <component :is="'form'" @submit.prevent="emit('submit')"><slot /></component>
  <!-- #endif -->
  <!-- #ifndef H5 -->
  <form @submit="emit('submit')"><slot /></form>
  <!-- #endif -->
</template>
