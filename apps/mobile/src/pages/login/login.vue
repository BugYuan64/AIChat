<template>
  <view class="login-shell">
    <!-- 桌面端(H5 ≥900px)左侧品牌面板:品牌大字逐词渐入(参考 management 登录页动效,配色改为模板青绿) -->
    <view class="brand-panel">
      <view class="panel-mark fade-item d1">AIChat</view>
      <view class="panel-words">
        <text class="panel-word fade-item d2" style="--target-opacity: 0.95">AI</text>
        <text class="panel-word fade-item d3" style="--target-opacity: 0.55">CHAT</text>
        <view class="panel-tagline fade-item d4">和人类、AI,一起把事情聊清楚。</view>
      </view>
    </view>

    <view class="form-side">
      <!-- 移动端品牌区(同样的渐入节奏) -->
      <view class="brand">
        <view class="brand-logo fade-item d1">AI</view>
        <view class="brand-title fade-item d2">AIChat</view>
        <view class="brand-sub fade-item d3">和人类、AI,一起把事情聊清楚</view>
      </view>

      <view class="card login-card">
        <view class="mode-tabs">
          <text :class="['mode-tab', mode === 'login' ? 'active' : '']" @tap="mode = 'login'">登录</text>
          <text :class="['mode-tab', mode === 'register' ? 'active' : '']" @tap="mode = 'register'">邀请注册</text>
        </view>

        <view v-if="mode === 'register'" class="field">
          <view class="field-label">邀请码</view>
          <input v-model="inviteCode" class="input" placeholder="由管理员提供" />
        </view>
        <view class="field">
          <view class="field-label">账号名</view>
          <input v-model="handle" class="input" placeholder="唯一,不可重复" :maxlength="64" />
        </view>
        <view v-if="mode === 'register'" class="field">
          <view class="field-label">昵称</view>
          <input v-model="displayName" class="input" placeholder="对外展示的名称" :maxlength="64" />
        </view>
        <view class="field">
          <view class="field-label">密码</view>
          <input v-model="password" class="input" password placeholder="输入密码" :maxlength="128" />
        </view>

        <view class="btn btn-primary" :class="{ 'btn-disabled': submitting }" @tap="submit">
          {{ submitting ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录' }}
        </view>

        <view class="advanced-toggle link" @tap="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '收起服务器设置' : '服务器设置' }}
        </view>
        <view v-if="showAdvanced" class="advanced">
          <view class="field">
            <view class="field-label">服务器地址(REST + WSS 同源)</view>
            <input v-model="serverBase" class="input" placeholder="例如 http://192.168.1.10:8000" />
          </view>
          <view class="btn btn-ghost btn-small" @tap="saveServerBase">保存地址</view>
          <view class="advanced-tip">默认 {{ defaultBase }};修改后立即生效,可在「我的」页再次更改。</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import { describeError, getServerBase, setServerBase } from '../../api/client';

const authStore = useAuthStore();

const mode = ref<'login' | 'register'>('login');
const showAdvanced = ref(false);
const defaultBase = getServerBase();
const serverBase = ref(defaultBase);

const handle = ref('');
const password = ref('');
const inviteCode = ref('');
const displayName = ref('');
const submitting = ref(false);

onShow(() => {
  // 已登录(含 401 刷新成功后的 reLaunch 回跳)直接进入会话 tab
  authStore.loadFromStorage();
  if (authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/sessions/sessions' });
  }
});

function saveServerBase() {
  try {
    const normalized = setServerBase(serverBase.value);
    serverBase.value = normalized;
    uni.showToast({ title: '已保存', icon: 'success' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

async function submit() {
  if (submitting.value) return;
  const h = handle.value.trim();
  if (!h || !password.value) {
    uni.showToast({ title: '请输入账号名和密码', icon: 'none' });
    return;
  }
  submitting.value = true;
  try {
    if (mode.value === 'login') {
      await authStore.login(h, password.value);
    } else {
      if (!inviteCode.value.trim() || !displayName.value.trim()) {
        uni.showToast({ title: '请填写邀请码和昵称', icon: 'none' });
        return;
      }
      await authStore.register({
        invite_code: inviteCode.value.trim(),
        handle: h,
        display_name: displayName.value.trim(),
        password: password.value,
      });
      await authStore.login(h, password.value);
    }
    uni.reLaunch({ url: '/pages/sessions/sessions' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  } finally {
    submitting.value = false;
  }
}
</script>

<style lang="scss" scoped>
/* ---- 品牌渐入动效(逐词错峰:0.1s / 0.35s / 0.6s,0.8s ease-out) ---- */
@keyframes brand-fade-in {
  0% {
    opacity: 0;
    transform: translateY(-8px);
  }
  100% {
    opacity: var(--target-opacity, 1);
    transform: translateY(0);
  }
}
.fade-item {
  opacity: 0;
  animation: brand-fade-in 0.8s ease-out both;
}
.d1 {
  animation-delay: 0.1s;
}
.d2 {
  animation-delay: 0.35s;
}
.d3 {
  animation-delay: 0.6s;
}
.d4 {
  animation-delay: 0.8s;
}
@media (prefers-reduced-motion: reduce) {
  .fade-item {
    animation: none;
    opacity: var(--target-opacity, 1);
  }
  .brand-logo {
    animation: none;
  }
}

.login-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--canvas);
}
/* 桌面品牌面板:移动端隐藏,≥900px 显示 */
.brand-panel {
  display: none;
}

/* ---- 移动端品牌区 ---- */
.form-side {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 80rpx 32rpx 60rpx;
  box-sizing: border-box;
}
.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 56rpx;
}
@keyframes logo-pulse {
  0%,
  100% {
    transform: scale(1);
    box-shadow: 0 12rpx 32rpx rgba(33, 106, 80, 0.25);
  }
  50% {
    transform: scale(1.045);
    box-shadow: 0 16rpx 44rpx rgba(33, 106, 80, 0.4);
  }
}
.brand-logo {
  width: 120rpx;
  height: 120rpx;
  border-radius: 32rpx;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 48rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12rpx 32rpx rgba(33, 106, 80, 0.25);
  animation: logo-pulse 2.8s ease-in-out 1.6s infinite;
}
.brand-title {
  font-size: 44rpx;
  font-weight: 700;
  letter-spacing: -0.5rpx;
  margin-top: 24rpx;
}
.brand-sub {
  font-size: 24rpx;
  color: var(--text-secondary);
  margin-top: 10rpx;
}

.login-card {
  margin: 0;
}
.mode-tabs {
  display: flex;
  gap: 8rpx;
  background: var(--surface-soft);
  border-radius: 20rpx;
  padding: 6rpx;
  margin-bottom: 32rpx;
}
.mode-tab {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  border-radius: 14rpx;
  color: var(--text-secondary);
  font-size: 28rpx;
}
.mode-tab.active {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: 0 2rpx 8rpx var(--shade);
}
.advanced-toggle {
  text-align: center;
  margin-top: 24rpx;
}
.advanced {
  margin-top: 20rpx;
  background: var(--surface-soft);
  border-radius: 20rpx;
  padding: 24rpx;
}
.advanced-tip {
  font-size: 22rpx;
  color: var(--text-faint);
  margin-top: 14rpx;
}

/* ---- 桌面端左右分栏 ---- */
@media (min-width: 900px) {
  .login-shell {
    flex-direction: row;
  }
  .brand {
    display: none;
  }
  .brand-panel {
    display: flex;
    flex: 1 1 54%;
    flex-direction: column;
    background: var(--accent);
    padding: 56px 64px;
    box-sizing: border-box;
  }
  .panel-mark {
    color: var(--on-accent);
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }
  .panel-words {
    margin: auto 0;
  }
  .panel-word {
    display: block;
    font-size: clamp(72px, 9.5vw, 136px);
    font-weight: 900;
    letter-spacing: -0.03em;
    line-height: 1.04;
    color: var(--on-accent);
  }
  .panel-tagline {
    margin-top: 28px;
    font-size: 16px;
    line-height: 1.7;
    color: rgba(255, 255, 255, 0.78);
    max-width: 340px;
  }
  .form-side {
    flex: 0 0 46%;
    justify-content: center;
    padding: 48px 56px;
  }
  .login-card {
    width: 100%;
    max-width: 400px;
    margin: 0 auto;
  }
}
</style>
