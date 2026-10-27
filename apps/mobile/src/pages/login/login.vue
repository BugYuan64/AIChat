<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import { describeError, getServerBase, setServerBase } from '../../api/client';
import UiIcon from '../../components/ui/UiIcon.vue';
import UiButton from '../../components/ui/UiButton.vue';
import InlineNotice from '../../components/ui/InlineNotice.vue';
import BottomSheet from '../../components/ui/BottomSheet.vue';
import AuthField from './AuthField.vue';
import AuthForm from './AuthForm.vue';
import NativeButton from '../../components/ui/NativeButton.vue';
import { loginCopy, validateAuthForm, type AuthFieldErrors, type AuthMode } from './model';

const auth = useAuthStore();
const mode = ref<AuthMode>('login');
const copy = computed(() => loginCopy(mode.value));
const fields = reactive({ handle: '', password: '', inviteCode: '', displayName: '' });
const errors = ref<AuthFieldErrors>({});
const submitting = ref(false);
const submitError = ref('');
const showPassword = ref(false);
const advanced = ref(false);
const recovery = ref(false);
const serverBase = ref(getServerBase());
const serverError = ref('');
const serverSaved = ref(false);
const focusField = ref('');
watch(mode, () => {
  uni.setNavigationBarTitle({ title: copy.value.title });
  // #ifdef H5
  document.title = copy.value.title;
  // #endif
  errors.value = {};
  submitError.value = '';
}, { immediate: true });
onShow(() => {
  auth.loadFromStorage();
  if (auth.isLoggedIn) uni.reLaunch({ url: '/pages/sessions/sessions' });
});
function clearError(key: keyof AuthFieldErrors) {
  delete errors.value[key];
  submitError.value = '';
}
async function focus(key: string) {
  focusField.value = '';
  await nextTick();
  focusField.value = key;
  // #ifdef H5
  document.getElementById('auth-' + key)?.focus();
  // #endif
}
function saveServer() {
  serverSaved.value = false;
  try {
    serverBase.value = setServerBase(serverBase.value);
    serverError.value = '';
    serverSaved.value = true;
  } catch (e) {
    serverError.value = describeError(e);
    void focus('server');
  }
}
async function submit() {
  if (submitting.value) return;
  errors.value = validateAuthForm({ mode: mode.value, ...fields });
  const first = Object.keys(errors.value)[0];
  if (first) { void focus(first); return; }
  submitting.value = true;
  submitError.value = '';
  try {
    const handle = fields.handle.trim();
    if (mode.value === 'register') await auth.register({
      invite_code: fields.inviteCode.trim(), handle,
      display_name: fields.displayName.trim(), password: fields.password,
    });
    await auth.login(handle, fields.password);
    uni.reLaunch({ url: '/pages/sessions/sessions' });
  } catch (e) { submitError.value = describeError(e); }
  finally { submitting.value = false; }
}
</script>

<template>
  <view class="login-shell">
    <view class="brand-stage" aria-hidden="true">
      <view class="brand-top"><view class="brand-mark"><UiIcon name="sparkles" tone="inverse" /></view><text>AIChat</text></view>
      <view class="brand-copy">
        <text class="brand-kicker scene-enter s1">A SPACE FOR BETTER IDEAS</text>
        <text class="brand-word scene-enter s2">HUMAN</text>
        <text class="brand-word brand-word--violet scene-enter s3">AI</text>
        <text class="brand-word scene-enter s4">CHAT<span class="brand-period">.</span></text>
        <text class="brand-description scene-enter s5">和人类、AI，一起把事情聊清楚。</text>
      </view>
      <view class="network-scene scene-enter s5">
        <view class="network-line line-one"><view class="network-dot" /></view>
        <view class="network-line line-two"><view class="network-dot" /></view>
        <view class="scene-node node-human"><UiIcon name="user-round" :size="24" /><text>你</text></view>
        <view class="scene-node node-ai"><UiIcon name="bot" tone="primary" :size="26" /><text>AI 搭档</text></view>
        <view class="scene-node node-group"><UiIcon name="users" :size="24" /><text>团队</text></view>
        <view class="message-chip chip-one">把想法发出来</view>
        <view class="message-chip chip-two"><view class="live-dot" />一起理清下一步</view>
      </view>
      <text class="brand-footer">THINK TOGETHER. MOVE FORWARD.</text>
    </view>
    <view class="auth-side">
      <view class="mobile-brand"><view class="brand-mark"><UiIcon name="sparkles" tone="inverse" /></view><text>AIChat</text></view>
      <view class="auth-card">
        <text class="auth-eyebrow">{{ mode === 'login' ? 'WELCOME BACK' : 'INVITATION ONLY' }}</text>
        <!-- #ifdef H5 -->
        <h1 class="auth-title">{{ copy.heading }}</h1>
        <!-- #endif -->
        <!-- #ifndef H5 -->
        <view class="auth-title" role="heading" aria-level="1">{{ copy.heading }}</view>
        <!-- #endif -->
        <text class="auth-description">{{ mode === 'login' ? '继续你与团队、AI 的对话。' : '使用管理员提供的邀请码加入协作。' }}</text>
        <view class="mode-tabs" role="tablist" aria-label="账号访问方式">
          <NativeButton type="button" class="mode-tab" :class="{ active: mode === 'login' }" role="tab" :aria-selected="mode === 'login'" @click="mode = 'login'">登录</NativeButton>
          <NativeButton type="button" class="mode-tab" :class="{ active: mode === 'register' }" role="tab" :aria-selected="mode === 'register'" @click="mode = 'register'">邀请注册</NativeButton>
        </view>
        <InlineNotice v-if="submitError" class="auth-error" tone="danger">{{ submitError }}</InlineNotice>
        <AuthForm @submit="submit">
          <AuthField v-if="mode === 'register'" id="auth-inviteCode" v-model="fields.inviteCode" label="邀请码" name="invitation-code" autocomplete="one-time-code" placeholder="管理员提供的邀请码" :error="errors.inviteCode" :focused="focusField === 'inviteCode'" @update:model-value="clearError('inviteCode')" />
          <AuthField id="auth-handle" v-model="fields.handle" label="账号名" name="username" autocomplete="username" :placeholder="copy.accountPlaceholder" :error="errors.handle" :focused="focusField === 'handle'" @update:model-value="clearError('handle')" />
          <AuthField v-if="mode === 'register'" id="auth-displayName" v-model="fields.displayName" label="昵称" name="name" autocomplete="name" placeholder="对外展示的名称" :error="errors.displayName" :focused="focusField === 'displayName'" @update:model-value="clearError('displayName')" />
          <view class="password-wrap">
            <AuthField id="auth-password" v-model="fields.password" label="密码" name="password" :autocomplete="copy.passwordAutocomplete" :type="showPassword ? 'text' : 'password'" :placeholder="mode === 'login' ? '输入密码' : '设置登录密码'" :error="errors.password" :focused="focusField === 'password'" @update:model-value="clearError('password')" />
            <NativeButton type="button" class="password-toggle" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</NativeButton>
          </view>
          <UiButton class="auth-submit" native-type="submit" size="large" :loading="submitting">{{ mode === 'login' ? '登录' : '注册并登录' }}<UiIcon name="arrow-left" class="submit-arrow" tone="inverse" :size="18" /></UiButton>
        </AuthForm>
        <view class="auth-links">
          <NativeButton type="button" class="text-button" @click="recovery = true">忘记密码？</NativeButton>
          <NativeButton type="button" class="text-button" :aria-expanded="advanced" @click="advanced = !advanced">{{ advanced ? '收起服务器设置' : '服务器设置' }}</NativeButton>
        </view>
        <view v-if="advanced" class="advanced motion-enter">
          <view class="advanced-heading"><text>自托管服务器</text><UiIcon name="server" tone="primary" :size="18" /></view>
          <AuthField id="auth-server" v-model="serverBase" label="服务器地址" name="server-origin" autocomplete="url" placeholder="https://chat.example.com" :error="serverError" :focused="focusField === 'server'" @update:model-value="serverError = ''; serverSaved = false" />
          <UiButton variant="secondary" size="small" @click="saveServer">保存地址</UiButton>
          <text v-if="serverSaved" class="saved" role="status">已保存并立即生效</text>
          <text class="advanced-hint">只填写协议、域名或 IP 和端口。REST 与 WSS 使用同一地址。</text>
        </view>
      </view>
      <text class="privacy-note">每个想法，都值得好好聊一聊。</text>
    </view>
    <BottomSheet :open="recovery" title="账号访问帮助" @close="recovery = false">
      <view class="recovery-copy"><UiIcon name="shield-check" tone="primary" :size="32" /><text class="recovery-title">联系管理员重置账号访问</text><text>当前没有自助找回服务。请联系为你提供邀请码或服务器地址的管理员。请勿向他人发送现有密码。</text></view>
      <template #footer><UiButton class="auth-submit" @click="recovery = false">我知道了</UiButton></template>
    </BottomSheet>
  </view>
</template>

<style scoped lang="scss">
.login-shell { min-height: 100vh; min-height: 100dvh; display: flex; background: var(--surface); }
.brand-stage { position: relative; display: none; flex: 1 1 55%; min-width: 0; padding: 36px 48px; overflow: hidden; background: radial-gradient(circle at 85% 20%, #ded4f4 0, transparent 27%), radial-gradient(circle at 10% 90%, #cddfc9 0, transparent 32%), #eaf4df; border-right: 1px solid var(--line-strong); }
.brand-top, .mobile-brand { display: flex; align-items: center; gap: 11px; font-size: 20px; font-weight: 800; letter-spacing: -0.04em; }
.brand-mark { width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; background: var(--accent-strong); border-radius: 13px; box-shadow: 0 6px 0 #c7d6c2; }
.brand-copy { position: relative; z-index: 2; margin-top: clamp(42px, 9vh, 94px); }
.brand-kicker { display: block; margin-bottom: 22px; font-size: 11px; letter-spacing: 0.15em; font-weight: 750; color: var(--accent); }
.brand-word { display: block; font-size: clamp(64px, 7.7vw, 112px); line-height: 0.87; font-weight: 900; letter-spacing: -0.07em; color: #102a22; }
.brand-word--violet { color: #9c7ce2; }
.brand-period { color: #9c7ce2; }
.brand-description { display: block; margin-top: 28px; font-size: 15px; color: var(--text-secondary); }
.brand-footer { position: absolute; left: 48px; bottom: 26px; color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: 0.13em; }
.scene-enter { animation: ui-rise 800ms var(--ease-out) both; }
.s1 { animation-delay: 100ms; }.s2 { animation-delay: 220ms; }.s3 { animation-delay: 350ms; }.s4 { animation-delay: 480ms; }.s5 { animation-delay: 600ms; }
.network-scene { position: absolute; width: 320px; height: 190px; bottom: 66px; right: 28px; }
.scene-node { position: absolute; z-index: 2; width: 60px; height: 66px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 5px; border: 1px solid #7d8e7e; border-radius: 18px; background: var(--surface); box-shadow: 0 5px 0 rgba(16,42,34,0.13); font-size: 10px; font-weight: 700; animation: ui-float 4s ease-in-out infinite; }
.node-human { left: 0; bottom: 20px; }.node-ai { left: 130px; top: 0; background: #ddeddd; animation-delay: -1.3s; }.node-group { right: 0; bottom: 32px; background: #e6dcfa; animation-delay: -2.5s; }
.network-line { position: absolute; height: 1px; background: #9aad96; transform-origin: left; }
.line-one { left: 49px; bottom: 82px; width: 126px; transform: rotate(-35deg); }.line-two { left: 179px; top: 57px; width: 103px; transform: rotate(36deg); }
.network-dot { width: 7px; height: 7px; margin-top: -3px; border-radius: 50%; background: var(--accent); animation: travel 3.2s ease-in-out infinite; }.line-two .network-dot { animation-delay: -1.6s; }
@keyframes travel { 0% { opacity: 0; transform: translateX(0); } 15%,85% { opacity: 1; } 100% { opacity: 0; transform: translateX(100px); } }
.message-chip { position: absolute; z-index: 3; padding: 10px 13px; border: 1px solid #a1afa0; border-radius: 12px; background: var(--surface); font-size: 11px; box-shadow: var(--shadow-soft); animation: ui-float 5s ease-in-out infinite; }
.chip-one { left: 0; top: 34px; }.chip-two { right: 0; top: 95px; display: flex; align-items: center; gap: 6px; color: var(--violet); animation-delay: -2s; }.live-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--violet); animation: ui-pulse 2s infinite; }
.auth-side { flex: 1 1 45%; min-width: 0; padding: 32px clamp(20px, 5vw, 66px); display: flex; flex-direction: column; justify-content: center; }
.mobile-brand { width: min(100%, 420px); margin: 0 auto 32px; }
.auth-card { width: min(100%, 420px); margin: auto; }
.auth-eyebrow { display: block; margin-bottom: 8px; color: var(--accent); font-size: 11px; font-weight: 800; letter-spacing: 0.14em; }
.auth-title { margin: 0; font-size: 34px; line-height: 1.2; font-weight: 800; letter-spacing: -0.04em; color: var(--text); }
.auth-description { display: block; margin-top: 9px; color: var(--text-secondary); font-size: 14px; line-height: 1.6; }
.mode-tabs { display: flex; padding: 5px; margin: 26px 0 22px; gap: 5px; border: 1px solid var(--line); border-radius: 16px; background: var(--surface-soft); }
.mode-tab { flex: 1; min-height: 42px; margin: 0; padding: 0; border: 0; border-radius: 11px; background: transparent; color: var(--text-secondary); font-size: 14px; font-weight: 650; line-height: 1; }
.mode-tab::after, .text-button::after, .password-toggle::after { display: none; }
.mode-tab.active { color: var(--text); background: var(--surface); box-shadow: 0 3px 10px rgba(25,45,34,0.08); }
.mode-tab:focus-visible, .text-button:focus-visible, .password-toggle:focus-visible { outline: 3px solid var(--focus-ring); outline-offset: 2px; }
.auth-error { margin-bottom: 18px; }.auth-submit { width: 100%; }.submit-arrow { transform: rotate(180deg); margin-left: 5px; }
.password-wrap { position: relative; }.password-toggle { position: absolute; top: 26px; right: 5px; min-height: 44px; padding: 0 11px; margin: 0; border: 0; background: transparent; color: var(--accent); font-size: 12px; line-height: 1; }
.auth-links { display: flex; justify-content: space-between; gap: 12px; margin-top: 8px; }.text-button { min-height: 44px; padding: 0; margin: 0; border: 0; background: transparent; color: var(--accent); font-size: 12px; line-height: 1; }
.advanced { margin-top: 12px; padding: 16px; border: 1px solid var(--line); border-radius: 18px; background: var(--surface-soft); }.advanced-heading { display: flex; justify-content: space-between; margin-bottom: 16px; font-size: 14px; font-weight: 750; }.advanced-hint { display: block; margin-top: 12px; font-size: 11px; line-height: 1.6; color: var(--text-secondary); }.saved { margin-left: 10px; font-size: 11px; color: var(--success); }
.privacy-note { display: block; padding-top: 30px; text-align: center; font-size: 11px; color: var(--text-secondary); }
.recovery-copy { display: flex; flex-direction: column; align-items: center; gap: 15px; padding: 24px; color: var(--text-secondary); font-size: 14px; line-height: 1.7; text-align: center; }.recovery-title { color: var(--text); font-size: 18px; font-weight: 750; }
@media (min-width: 900px) { .brand-stage { display: block; }.auth-side { flex: 0 0 45%; height: 100vh; height: 100dvh; overflow-y: auto; }.mobile-brand { display: none; }.auth-card { margin: auto; }.privacy-note { padding-top: 16px; } }
@media (max-width: 380px) { .auth-side { padding: 22px 16px; }.auth-title { font-size: 30px; }.mobile-brand { margin-bottom: 24px; } }
@media (prefers-reduced-motion: reduce) { .scene-enter, .scene-node, .message-chip, .network-dot, .live-dot { animation: none !important; opacity: 1; } }
</style>
