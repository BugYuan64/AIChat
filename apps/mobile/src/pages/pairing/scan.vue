<template>
  <view class="page stagger">
    <!-- 输入 / 扫码进入 -->
    <view class="card">
      <view class="field">
        <view class="field-label">方式一：扫描连接器展示的二维码</view>
        <view class="btn btn-primary" @tap="scan">扫码</view>
      </view>
      <view class="divider" />
      <view class="field">
        <view class="field-label">方式二：输入配对码（同机使用无需摄像头）</view>
        <view class="manual-row">
          <input v-model="pidInput" class="input" placeholder="pairing_id（pid）" />
          <input v-model="codeInput" class="input" placeholder="短码 short_code" />
          <view class="btn btn-ghost btn-small" @tap="loadByInput">查询</view>
        </view>
      </view>
    </view>

    <!-- 配对信息 -->
    <template v-if="info">
      <view class="card">
        <view class="pair-title">连接器信息</view>
        <view class="kv"><text class="k">名称</text><text class="v">{{ info.connector_name }}</text></view>
        <view class="kv"><text class="k">平台</text><text class="v">{{ info.platform || '-' }}</text></view>
        <view class="kv"><text class="k">请求能力</text><text class="v">{{ info.requested_capabilities?.join('、') || '-' }}</text></view>
        <view class="kv"><text class="k">目标 AI</text><text class="v">{{ info.agent_display_name || info.agent_id }}</text></view>
        <view class="kv"><text class="k">状态</text><text class="v">{{ statusText(info.status) }}</text></view>
        <view class="kv"><text class="k">有效期至</text><text class="v">{{ formatTime(info.expires_at) }}{{ expireInText }}</text></view>
      </view>

      <!-- 确认码核对 -->
      <view class="card confirm-card">
        <view class="field-label">请与本机（连接器设备）屏幕上显示的确认码核对：</view>
        <view class="confirm-code">{{ info.confirm_code }}</view>
        <view class="confirm-check" @tap="confirmed = !confirmed">
          <view class="checkbox" :class="{ checked: confirmed }">{{ confirmed ? '✓' : '' }}</view>
          <text>我已核对连接器本机显示的确认码一致（防止他人抢扫公开终端二维码）</text>
        </view>
      </view>

      <!-- 选择本人 AI -->
      <view class="card">
        <view class="field-label">绑定到我的 AI（默认使用配对单上的目标 AI）</view>
        <view v-for="a in ownedAgents" :key="a.agent_id" class="agent-opt" @tap="selectedAgentId = a.agent_id">
          <view class="checkbox" :class="{ checked: selectedAgentId === a.agent_id }">{{ selectedAgentId === a.agent_id ? '✓' : '' }}</view>
          <view class="list-body">
            <view class="row-line">
              <text class="list-title">{{ a.display_name }}</text>
              <text class="tag tag-ai">AI</text>
            </view>
            <view class="list-sub">@{{ a.handle }}</view>
          </view>
        </view>
        <view v-if="!ownedAgents.length" class="list-sub">你没有 AI 账号，请先到「我的 AI」创建</view>
      </view>

      <!-- 决策 -->
      <view class="card" v-if="info.status === 'pending_user'">
        <view class="btn btn-primary" :class="{ 'btn-disabled': !canDecide || deciding }" @tap="decide('approve')">
          {{ deciding ? '提交中…' : '批准配对' }}
        </view>
        <view class="btn btn-danger" :class="{ 'btn-disabled': !canDecide || deciding }" @tap="decide('deny')">拒绝</view>
        <view class="foot-tip">批准后连接器还需其本机操作者再次确认（pending_local → approved），随后自动兑换凭据上线。</view>
      </view>
      <view class="card" v-else>
        <view class="foot-tip">当前状态：{{ statusText(info.status) }}。此页每 5 秒自动刷新，可留在本页等待状态变化。</view>
      </view>
    </template>

    <view v-else-if="loadError" class="empty">{{ loadError }}</view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onHide, onLoad, onShow } from '@dcloudio/uni-app';
import * as pairingApi from '../../api/pairing';
import * as agentsApi from '../../api/agents';
import { describeError } from '../../api/client';
import { formatTime } from '../../utils/misc';
import type { Agent, PairingInfo, PairingStatus } from '../../api/types';

const pidInput = ref('');
const codeInput = ref('');
/** 当前载入的配对（轮询用，避免输入框被清空后拿错参数） */
const activePid = ref('');
const activeCode = ref('');

const info = ref<PairingInfo | null>(null);
const loadError = ref('');
const ownedAgents = ref<Agent[]>([]);
const selectedAgentId = ref('');
const confirmed = ref(false);
const deciding = ref(false);

let pollTimer: ReturnType<typeof setInterval> | null = null;

const canDecide = computed(() => confirmed.value && !!selectedAgentId.value && info.value?.status === 'pending_user');
const expireInText = computed(() => {
  if (!info.value?.expires_at) return '';
  const ms = new Date(info.value.expires_at).getTime() - Date.now();
  if (Number.isNaN(ms)) return '';
  if (ms <= 0) return '（已过期）';
  return `（剩 ${Math.ceil(ms / 60000)} 分钟）`;
});

onLoad(async (options) => {
  // 支持从外部 qr_payload 直接带入：/pages/pairing/scan?pid=...&code=...
  const pid = options?.pid;
  const code = options?.code;
  if (pid && code) {
    pidInput.value = pid;
    codeInput.value = code;
    await loadPairing(pid, code);
  }
  await loadAgents();
});

onShow(() => startPolling());
onHide(() => stopPolling());

function startPolling() {
  stopPolling();
  // 规约默认轮询间隔 5 秒
  pollTimer = setInterval(() => void pollRefresh(), 5000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function loadAgents() {
  try {
    const res = await agentsApi.listAgents('owned');
    ownedAgents.value = res.items ?? [];
    // 默认选中配对单上的目标 AI（若属于我），否则选第一个
    const preset = info.value?.agent_id;
    if (preset && ownedAgents.value.some((a) => a.agent_id === preset)) {
      selectedAgentId.value = preset;
    } else if (ownedAgents.value.length && !selectedAgentId.value) {
      selectedAgentId.value = ownedAgents.value[0].agent_id;
    }
  } catch {
    // 列表失败不阻塞核对流程
  }
}

async function loadPairing(pid: string, code: string) {
  loadError.value = '';
  try {
    const p = pid.trim();
    const c = code.trim();
    info.value = await pairingApi.getPairing(p, c);
    activePid.value = p;
    activeCode.value = c;
    await loadAgents();
  } catch (e) {
    info.value = null;
    loadError.value = describeError(e);
  }
}

function loadByInput() {
  if (!pidInput.value.trim() || !codeInput.value.trim()) {
    uni.showToast({ title: '请填写 pairing_id 与短码', icon: 'none' });
    return;
  }
  void loadPairing(pidInput.value, codeInput.value);
}

/** 解析 qr_payload：https://<host>/pair?pid=<pairing_id>&code=<short_code>（不含秘密） */
function parseQrPayload(text: string): { pid?: string; code?: string } {
  const pid = /[?&]pid=([^&#\s]+)/.exec(text)?.[1];
  const code = /[?&]code=([^&#\s]+)/.exec(text)?.[1];
  return { pid: pid && decodeURIComponent(pid), code: code && decodeURIComponent(code) };
}

function scan() {
  uni.scanCode({
    scanType: ['qrCode'],
    success: (res) => {
      const { pid, code } = parseQrPayload(res.result || '');
      if (!pid || !code) {
        uni.showToast({ title: '二维码格式不正确', icon: 'none' });
        return;
      }
      pidInput.value = pid;
      codeInput.value = code;
      void loadPairing(pid, code);
    },
    fail: () => {
      // 用户取消或无权限：保持输入方式
    },
  });
}

async function pollRefresh() {
  if (!info.value) return;
  const terminal: PairingStatus[] = ['redeemed', 'denied', 'expired', 'cancelled'];
  if (terminal.includes(info.value.status)) {
    stopPolling();
    return;
  }
  try {
    info.value = await pairingApi.getPairing(activePid.value || info.value.pairing_id, activeCode.value);
  } catch {
    // 轮询失败静默，下轮重试
  }
}

async function decide(decision: 'approve' | 'deny') {
  if (!canDecide.value || !info.value || deciding.value) return;
  deciding.value = true;
  try {
    const res = await pairingApi.decidePairing(info.value.pairing_id, {
      decision,
      confirm_code: info.value.confirm_code, // 服务端下发，用户负责与本机显示核对
      expected_version: info.value.version,
      agent_id: selectedAgentId.value, // 可选字段：服务端不支持时忽略（§0 未知可选字段可忽略）
    });
    info.value = res ?? { ...info.value, status: decision === 'approve' ? 'pending_local' : 'denied' };
    uni.showToast({
      title: decision === 'approve' ? '已批准，等待连接器本机确认' : '已拒绝',
      icon: 'none',
    });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
    await pollRefresh(); // 可能是 VERSION_CONFLICT，刷新后可重试
  } finally {
    deciding.value = false;
  }
}

function statusText(s: PairingStatus): string {
  switch (s) {
    case 'pending_user':
      return '等待你批准';
    case 'pending_local':
      return '等待连接器本机确认';
    case 'approved':
      return '已批准，等待连接器兑换凭据';
    case 'redeemed':
      return '配对完成，连接器已上线';
    case 'denied':
      return '已拒绝';
    case 'expired':
      return '已过期';
    case 'cancelled':
      return '已取消';
    default:
      return s;
  }
}
</script>

<style lang="scss" scoped>
.manual-row {
  display: flex;
  gap: 12rpx;
  align-items: center;
  .input {
    flex: 1;
    min-width: 0;
  }
}
.pair-title {
  font-size: 30rpx;
  font-weight: 600;
  margin-bottom: 16rpx;
}
.confirm-card {
  background: var(--warning-soft);
  border-color: transparent;
}
.confirm-code {
  font-size: 72rpx;
  font-weight: 700;
  letter-spacing: 16rpx;
  text-align: center;
  color: var(--warning);
  margin: 24rpx 0;
  font-variant-numeric: tabular-nums;
  animation: pop-in 0.4s ease-out backwards;
}
.confirm-check {
  display: flex;
  align-items: flex-start;
  gap: 16rpx;
  font-size: 24rpx;
  color: var(--text-secondary);
}
.agent-opt {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--line);
  .checkbox {
    margin-right: 20rpx;
  }
}
.agent-opt:last-of-type {
  border-bottom: none;
}
.row-line {
  display: flex;
  align-items: center;
  min-width: 0;
}
.foot-tip {
  margin-top: 16rpx;
  font-size: 22rpx;
  color: var(--text-faint);
}
</style>
