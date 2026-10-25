<template>
  <view class="page login-page">
    <view class="brand">
      <view class="brand-logo">AI</view>
      <view class="brand-title">AIChat</view>
      <view class="brand-sub">人类与 AI 的聊天</view>
    </view>

    <view class="card">
      <view class="mode-tabs">
        <text :class="['mode-tab', mode === 'login' ? 'active' : '']" @tap="mode = 'login'">登录</text>
        <text :class="['mode-tab', mode === 'register' ? 'active' : '']" @tap="mode = 'register'">邀请注册</text>
      </view>

      <view v-if="mode === 'register'" class="field">
        <view class="field-label">邀请码</view>
        <input v-model="inviteCode" class="input" placeholder="由管理员提供" />
      </view>
      <view class="field">
        <view class="field-label">账号名（handle）</view>
        <input v-model="handle" class="input" placeholder="唯一，不可重复" :maxlength="64" />
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
          <view class="field-label">服务器地址（REST + WSS 同源）</view>
          <input v-model="serverBase" class="input" placeholder="例如 http://192.168.1.10:8000" />
        </view>
        <view class="btn btn-ghost btn-small" @tap="saveServerBase">保存地址</view>
        <view class="advanced-tip">默认 {{ defaultBase }}；修改后立即生效，可在「我的」页再次更改。</view>
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
  // 已登录（含 401 刷新成功后的 reLaunch 回跳）直接进入会话 tab
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
.login-page {
  padding-top: 100rpx;
}
.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 48rpx;
}
.brand-logo {
  width: 120rpx;
  height: 120rpx;
  border-radius: 28rpx;
  background: #3b82f6;
  color: #ffffff;
  font-size: 48rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-title {
  font-size: 40rpx;
  font-weight: 600;
  margin-top: 20rpx;
}
.brand-sub {
  font-size: 24rpx;
  color: #8a9099;
  margin-top: 8rpx;
}
.mode-tabs {
  display: flex;
  margin-bottom: 28rpx;
  border-bottom: 1rpx solid #f0f1f3;
}
.mode-tab {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  color: #8a9099;
  font-size: 28rpx;
}
.mode-tab.active {
  color: #3b82f6;
  font-weight: 600;
  border-bottom: 4rpx solid #3b82f6;
}
.advanced-toggle {
  text-align: center;
  margin-top: 24rpx;
}
.advanced {
  margin-top: 20rpx;
  background: #f8fafc;
  border-radius: 14rpx;
  padding: 20rpx;
}
.advanced-tip {
  font-size: 22rpx;
  color: #9aa0a6;
  margin-top: 14rpx;
}
</style>
