<script setup lang="ts">
withDefaults(defineProps<{ id: string; modelValue: string; label: string; name: string; autocomplete?: string; placeholder?: string; type?: string; error?: string; focused?: boolean }>(), { autocomplete: 'off', placeholder: '', type: 'text', error: '', focused: false });
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
function nativeInput(event: Event) { emit('update:modelValue', (event.target as HTMLInputElement).value); }
function uniInput(event: Event) { emit('update:modelValue', (event as unknown as { detail: { value: string } }).detail.value); }
</script>
<template>
  <view class="auth-field">
    <!-- #ifdef H5 -->
    <component :is="'label'" class="auth-field__label" :for="id">{{ label }}</component>
    <!-- #endif -->
    <!-- #ifndef H5 -->
    <label class="auth-field__label" :for="id">{{ label }}</label>
    <!-- #endif -->
    <!-- #ifdef H5 -->
    <component :is="'input'" :id="id" class="auth-field__input" :class="{ invalid: error }" :value="modelValue" :type="type" :name="name" :autocomplete="autocomplete" :placeholder="placeholder" :aria-invalid="!!error" :aria-describedby="error ? id + '-error' : undefined" @input="nativeInput" />
    <!-- #endif -->
    <!-- #ifndef H5 -->
    <input :id="id" class="auth-field__input" :class="{ invalid: error }" :value="modelValue" :name="name" :password="type === 'password'" :placeholder="placeholder" :focus="focused" :aria-label="label" @input="uniInput" />
    <!-- #endif -->
    <text v-if="error" :id="id + '-error'" class="auth-field__error" role="alert">{{ error }}</text>
  </view>
</template>
<style scoped>
.auth-field { margin-bottom: 18px; }.auth-field__label { display: block; margin-bottom: 7px; color: var(--text); font-size: 13px; font-weight: 650; }.auth-field__input { display: block; width: 100%; height: 48px; padding: 0 14px; border: 1px solid var(--control-line); border-radius: 13px; background: var(--surface-elevated); color: var(--text); font-size: 15px; box-sizing: border-box; outline: none; transition: border-color 140ms, box-shadow 140ms; }.auth-field__input[type=password] { padding-right: 60px; }.auth-field__input::placeholder { color: #68766d; opacity: 1; }.auth-field__input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(25,107,85,0.15); }.auth-field__input.invalid { border-color: var(--danger); }.auth-field__error { display: block; margin-top: 6px; color: var(--danger); font-size: 12px; line-height: 1.5; }
</style>
