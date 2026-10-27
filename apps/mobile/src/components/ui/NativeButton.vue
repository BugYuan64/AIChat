<script setup lang="ts">
import { computed, useAttrs, type StyleValue } from 'vue';
defineOptions({ inheritAttrs: false });
const attrs = useAttrs();
const nativeStyle = computed(() => attrs.style as StyleValue);
withDefaults(defineProps<{ type?: string; disabled?: boolean; formType?: 'submit' | 'reset'; ariaLabel?: string; ariaPressed?: boolean; ariaSelected?: boolean; ariaExpanded?: boolean; role?: string }>(), { type: 'button', disabled: false });
const emit = defineEmits<{ click: [event: Event] }>();
</script>
<template>
  <!-- #ifdef H5 -->
  <component :is="'button'" v-bind="$attrs" :class="['native-button', $attrs.class]" :type="type" :disabled="disabled" :aria-label="ariaLabel" :aria-pressed="ariaPressed" :aria-selected="ariaSelected" :aria-expanded="ariaExpanded" :role="role" @click="emit('click', $event)"><slot /></component>
  <!-- #endif -->
  <!-- #ifndef H5 -->
  <button :class="$attrs.class" :style="nativeStyle" :disabled="disabled" :form-type="formType" :aria-label="ariaLabel" @click="emit('click', $event)"><slot /></button>
  <!-- #endif -->
</template>
