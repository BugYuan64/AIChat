<script setup lang="ts">
import { computed } from 'vue';
import { iconSource, type UiIconName, type UiIconTone } from '../../ui/icons';

const props = withDefaults(defineProps<{
  name: UiIconName;
  tone?: UiIconTone;
  size?: number;
  label?: string;
}>(), { tone: 'default', size: 20, label: '' });

const source = computed(() => iconSource(props.name, props.tone));
const imageStyle = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }));
</script>

<template>
  <image
    class="ui-icon"
    :src="source"
    :style="imageStyle"
    mode="aspectFit"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
  />
</template>

<style scoped>
.ui-icon { display: inline-block; flex: 0 0 auto; vertical-align: middle; }
</style>
