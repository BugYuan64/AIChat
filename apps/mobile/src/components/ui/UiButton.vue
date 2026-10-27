<script setup lang="ts">
import UiIcon from './UiIcon.vue';
import NativeButton from './NativeButton.vue';
import type { UiIconName } from '../../ui/icons';

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'small' | 'medium' | 'large' | 'icon';
  loading?: boolean;
  disabled?: boolean;
  icon?: UiIconName;
  label?: string;
  nativeType?: 'button' | 'submit' | 'reset';
}>(), { variant: 'primary', size: 'medium', loading: false, disabled: false, icon: undefined, label: '', nativeType: 'button' });

const emit = defineEmits<{ click: [event: Event] }>();

function handleClick(event: Event) {
  if (!props.disabled && !props.loading) emit('click', event);
}
</script>

<template>
  <NativeButton
    class="ui-button"
    :class="[`ui-button--${variant}`, `ui-button--${size}`, { 'is-loading': loading }]"
    :type="nativeType"
    :form-type="nativeType === 'submit' ? 'submit' : undefined"
    :disabled="disabled || loading"
    :aria-label="label || undefined"
    @click="handleClick"
  >
    <UiIcon v-if="loading" class="ui-button__spinner" name="loader-circle" :tone="variant === 'primary' ? 'inverse' : 'muted'" :size="18" />
    <UiIcon v-else-if="icon" :name="icon" :tone="variant === 'primary' ? 'inverse' : variant === 'danger' ? 'danger' : 'default'" :size="18" />
    <text v-if="$slots.default" class="ui-button__label"><slot /></text>
  </NativeButton>
</template>

<style scoped lang="scss">
.ui-button {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  padding: 0 18px;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  background: var(--accent);
  color: var(--on-accent);
  font-size: 15px;
  font-weight: 650;
  line-height: 1;
  transition: transform var(--motion-fast) var(--ease-out), box-shadow var(--motion-fast) var(--ease-out), background var(--motion-fast) var(--ease-out);
}
.ui-button::after { display: none; }
.ui-button:not([disabled]):active { transform: translateY(1px) scale(0.985); }
.ui-button:focus-visible { outline: 3px solid var(--focus-ring); outline-offset: 2px; }
.ui-button[disabled] { opacity: 0.52; cursor: not-allowed; }
.ui-button--primary { box-shadow: 0 8px 20px rgba(25, 107, 85, 0.18); }
.ui-button--secondary { background: var(--surface); color: var(--text); border-color: var(--line-strong); }
.ui-button--ghost { background: transparent; color: var(--text); }
.ui-button--danger { background: var(--danger-soft); color: var(--danger); border-color: rgba(178, 59, 56, 0.16); }
.ui-button--small { min-height: 36px; padding: 0 13px; font-size: 13px; }
.ui-button--large { min-height: 50px; padding: 0 22px; }
.ui-button--icon { width: 44px; padding: 0; border-radius: 14px; }
.ui-button__spinner { animation: ui-spin 0.9s linear infinite; }
@media (max-width: 899px) { .ui-button--small { min-height: 44px; } }
@keyframes ui-spin { to { transform: rotate(360deg); } }
</style>
