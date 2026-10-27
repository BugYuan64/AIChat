<template>
  <PageLayout title="连接设备" eyebrow="CONNECT YOUR WORKSPACE" subtitle="把熟悉的设备，连接到你的 AI 搭档。" active="me" back :back-fallback="backFallback">
    <view class="pairing-steps"><view class="step" :class="{ complete: info }"><text class="step-number">01</text><text>获取配对请求</text></view><view class="step" :class="{ complete: confirmed }"><text class="step-number">02</text><text>核对与批准</text></view><view class="step" :class="{ complete: info?.status === 'redeemed' }"><text class="step-number">03</text><text>本机确认</text></view></view>
    <InlineNotice v-if="loadError" tone="danger">{{ loadError }}</InlineNotice>
    <view class="detail-grid">
      <view class="panel-stack">
        <SectionPanel title="从连接器发起" description="在连接器设备上创建配对请求，然后回到这里。" icon="scan-line" tone="mint">
          <view class="scan-illustration"><view class="scan-corners"><UiIcon name="scan-line" tone="primary" :size="64" /><view class="scan-sweep" /></view></view>
          <!-- #ifndef H5 -->
          <UiButton class="wide-button" icon="scan-line" @click="scan">扫描连接器二维码</UiButton>
          <!-- #endif -->
          <!-- #ifdef H5 -->
          <text class="panel-hint scan-browser-tip">浏览器中请使用下方配对码；移动客户端支持扫描二维码。</text>
          <!-- #endif -->
          <view class="manual-pairing"><text class="field-label">使用配对码连接</text><view class="field"><input v-model="pidInput" class="input" aria-label="配对请求 ID" placeholder="配对请求 ID（pid）" /></view><view class="field"><input v-model="codeInput" class="input" aria-label="配对短码" placeholder="连接器显示的短码" /></view><UiButton class="wide-button" variant="secondary" icon="search" :loading="lookupBusy" :disabled="deciding" @click="loadByInput">查询配对请求</UiButton></view>
        </SectionPanel>
        <SectionPanel v-if="info" title="核对连接信息" icon="shield-check">
          <view class="kv"><text class="k">连接器</text><text class="v">{{ info.connector_name }}</text></view><view class="kv"><text class="k">平台</text><text class="v">{{ info.platform || '未提供' }}</text></view><view class="kv"><text class="k">目标 AI</text><text class="v">{{ info.agent_display_name || info.agent_id }}</text></view><view class="kv"><text class="k">有效期</text><text class="v">{{ formatTime(info.expires_at) }} {{ expireInText }}</text></view>
          <UiButton variant="ghost" size="small" :icon="techOpen ? 'chevron-down' : 'chevron-right'" @click="techOpen = !techOpen">请求能力与技术信息</UiButton><view v-if="techOpen" class="technical-info"><text class="panel-hint">请求能力：{{ info.requested_capabilities?.join('、') || '未提供' }}</text><text class="technical-value">{{ info.pairing_id }}</text></view>
        </SectionPanel>
      </view>
      <view class="panel-stack">
        <template v-if="info">
          <SectionPanel title="确认是你要连接的设备" description="请与连接器本机屏幕上的确认码逐位核对。" tone="violet" icon="lock-keyhole">
            <view class="confirm-code">{{ info.confirm_code }}</view>
            <InlineNotice v-if="verifyStale" tone="warning" title="配对单已更新，请重新核对">确认码或版本已变化，此前的核对已作废。请与连接器本机屏幕重新逐位比对后再勾选。</InlineNotice>
            <NativeButton class="confirm-check" :aria-pressed="confirmed" @click="toggleConfirm"><view class="checkbox" :class="{ checked: confirmed }"><UiIcon v-if="confirmed" name="check" tone="inverse" :size="14" /></view><text>我已核对，两端的确认码一致</text></NativeButton>
          </SectionPanel>
          <SectionPanel title="选择你的 AI" description="设备将为选中的 AI 提供运行能力。" icon="bot">
            <NativeButton v-for="a in ownedAgents" :key="a.agent_id" class="agent-option" :aria-pressed="selectedAgentId === a.agent_id" @click="selectedAgentId = a.agent_id"><AccountAvatar :name="a.display_name" kind="agent" size="small" /><view class="data-copy"><text class="data-title">{{ a.display_name }}</text><text class="data-description">@{{ a.handle }}</text></view><view class="checkbox" :class="{ checked: selectedAgentId === a.agent_id }"><UiIcon v-if="selectedAgentId === a.agent_id" name="check" tone="inverse" :size="14" /></view></NativeButton>
            <EmptyState v-if="!ownedAgents.length" icon="bot" title="还没有可绑定的 AI" description="先到「我的 AI」创建一个账号。" />
          </SectionPanel>
          <SectionPanel :tone="info.status === 'redeemed' ? 'mint' : 'default'">
            <StatusBadge :tone="info.status === 'redeemed' ? 'success' : ['denied','expired','cancelled'].includes(info.status) ? 'danger' : 'warning'">{{ statusText(info.status) }}</StatusBadge>
            <view v-if="info.status === 'pending_user'" class="button-row"><UiButton :loading="deciding" :disabled="!canApprove" icon="shield-check" @click="decide('approve')">批准配对</UiButton><UiButton variant="danger" :disabled="!canDecide || deciding" @click="decide('deny')">拒绝</UiButton></view>
            <text class="pairing-status-note panel-hint">{{ info.status === 'redeemed' ? '两端确认完成，设备已完成接入。' : info.status === 'pending_user' ? '批准后，还需要连接器本机操作者再次确认。' : info.status === 'pending_local' ? '等待连接器本机操作者确认。此页每 5 秒自动更新。' : '配对状态会自动更新。过期后请在连接器重新发起。' }}</text>
          </SectionPanel>
        </template>
        <SectionPanel v-else title="安全地建立连接" icon="shield-check" tone="violet"><text class="panel-hint">配对需要两端共同确认。只批准你亲自发起、且确认码一致的连接请求。</text><view class="divider" /><text class="panel-hint">二维码用于定位请求。最终仍需核对确认码，并由连接器本机操作者再次批准。</text></SectionPanel>
      </view>
    </view>
  </PageLayout>
</template>
<script setup lang="ts">
import PageLayout from '../../components/layout/PageLayout.vue';
import SectionPanel from '../../components/ui/SectionPanel.vue';
import UiButton from '../../components/ui/UiButton.vue';
import NativeButton from '../../components/ui/NativeButton.vue';
import UiIcon from '../../components/ui/UiIcon.vue';
import AccountAvatar from '../../components/ui/AccountAvatar.vue';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import InlineNotice from '../../components/ui/InlineNotice.vue';
import EmptyState from '../../components/ui/EmptyState.vue';
import BottomSheet from '../../components/ui/BottomSheet.vue';

import { canApprovePairing } from '../../ui/operations';
import { computed, ref } from 'vue';
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app';
import * as pairingApi from '../../api/pairing';
import * as agentsApi from '../../api/agents';
import { describeError } from '../../api/client';
import { formatTime } from '../../utils/misc';
import type { BackFallback } from '../../utils/nav';
import type { Agent, PairingInfo, PairingStatus } from '../../api/types';

/** 深链直达时页面栈只有一层，返回键应回到「我的」而不是会话列表 */
const backFallback: BackFallback = { url: '/pages/me/me', tab: true };

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
/**
 * 用户勾选时亲手核对过的那一版配对单。
 * 轮询会把 confirm_code / version 换掉，屏幕上看到的码可能已经不是用户比对过的那个，
 * 所以批准时提交这份快照，而不是「此刻最新的值」。
 */
const verified = ref<{ pairing_id: string; confirm_code: string; version: number } | null>(null);
/** 核对结果被轮询作废后置真，用于提示用户重新比对；重新勾选即清除 */
const confirmRevoked = ref(false);
const deciding = ref(false);
const nowTick = ref(Date.now());
const techOpen = ref(false);

let lookupVersion = 0;
let pageVisible = true;
const lookupBusy = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

function currentTriple() {
  const p = info.value;
  return p ? { pairing_id: p.pairing_id, confirm_code: p.confirm_code, version: p.version } : null;
}

/** 屏幕上的配对单是否仍是用户核对过的那一版 */
function sameAsVerified(): boolean {
  const v = verified.value, now = currentTriple();
  return !!v && !!now && now.pairing_id === v.pairing_id && now.confirm_code === v.confirm_code && now.version === v.version;
}

/** 作废核对结果：切换配对单、或轮询换掉了确认码/版本时调用 */
function revokeConfirm(warn = true) {
  if (warn && (confirmed.value || verified.value)) confirmRevoked.value = true;
  confirmed.value = false;
  verified.value = null;
}

/** 勾选即锁定当前这一版，取消勾选则丢弃 */
function toggleConfirm() {
  if (confirmed.value) {
    revokeConfirm(false);
    return;
  }
  const triple = currentTriple();
  if (!triple) return;
  confirmRevoked.value = false;
  confirmed.value = true;
  verified.value = triple;
}

/** 勾选后配对单被换掉：需要重新核对 */
const verifyStale = computed(() => confirmRevoked.value || (confirmed.value && !sameAsVerified()));

const canDecide = computed(() => canApprovePairing({ confirmed: confirmed.value, agentId: selectedAgentId.value, status: info.value?.status, expiresAt: info.value?.expires_at, now: nowTick.value }));
/**
 * 批准额外要求「当前这一版就是用户核对过的那一版」。
 * 拒绝沿用 canDecide（与原实现一致，同样要求先勾选），只是不使用核对快照——它提交的是当前这一版。
 */
const canApprove = computed(() => canDecide.value && sameAsVerified());
const expireInText = computed(() => {
  if (!info.value?.expires_at) return '';
  const ms = new Date(info.value.expires_at).getTime() - nowTick.value;
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

onShow(() => { pageVisible = true; nowTick.value = Date.now(); startPolling(); });
onHide(() => { pageVisible = false; stopPolling(); });
onUnload(() => { pageVisible = false; ++lookupVersion; stopPolling(); });

function startPolling() {
  stopPolling();
  // 规约默认轮询间隔 5 秒
  pollTimer = setInterval(() => { nowTick.value = Date.now(); void pollRefresh(); }, 5000);
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
  if (deciding.value) return;
  const version = ++lookupVersion;
  stopPolling();
  lookupBusy.value = true;
  loadError.value = '';
  revokeConfirm(false);
  info.value = null;
  activePid.value = '';
  activeCode.value = '';
  selectedAgentId.value = '';
  nowTick.value = Date.now();
  try {
    const p = pid.trim(), c = code.trim();
    const result = await pairingApi.getPairing(p, c);
    if (version !== lookupVersion) return;
    info.value = result;
    revokeConfirm(false);
    activePid.value = p;
    activeCode.value = c;
    await loadAgents();
    if (version === lookupVersion && pageVisible) startPolling();
  } catch (e) {
    if (version === lookupVersion) { info.value = null; loadError.value = describeError(e); }
  } finally { if (version === lookupVersion) lookupBusy.value = false; }
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
  try { return { pid: pid && decodeURIComponent(pid), code: code && decodeURIComponent(code) }; } catch { return {}; }
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
  if (!info.value || lookupBusy.value || deciding.value) return;
  const terminal: PairingStatus[] = ['redeemed', 'denied', 'expired', 'cancelled'];
  if (terminal.includes(info.value.status)) { stopPolling(); return; }
  const version = lookupVersion, pid = activePid.value, code = activeCode.value;
  try {
    const result = await pairingApi.getPairing(pid, code);
    if (version !== lookupVersion || activePid.value !== pid || deciding.value || !pageVisible) return;
    if (info.value && result.version < info.value.version) return;
    // 服务端换掉了确认码/版本：用户核对过的那一版已经不存在，勾选随之作废
    const rotated = info.value?.confirm_code !== result.confirm_code
      || info.value?.version !== result.version
      || info.value?.pairing_id !== result.pairing_id;
    if (rotated) revokeConfirm(true);
    info.value = result;
  } catch { /* A later poll retries transient failures. */ }
}

async function decide(decision: 'approve' | 'deny') {
  nowTick.value = Date.now();
  if (!canDecide.value || !info.value || deciding.value || lookupBusy.value) return;
  // 批准必须落在用户亲手核对过的那一版上，否则宁可让用户重新勾选
  if (decision === 'approve' && !sameAsVerified()) return;
  const target = decision === 'approve' ? verified.value : currentTriple();
  if (!target) return;
  deciding.value = true;
  try {
    const res = await pairingApi.decidePairing(target.pairing_id, {
      decision,
      confirm_code: target.confirm_code, // 用户核对过的那一版，不是轮询后最新的值
      expected_version: target.version,
      agent_id: selectedAgentId.value, // 可选字段：服务端不支持时忽略（§0 未知可选字段可忽略）
    });
    revokeConfirm(false);
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
    await pollRefresh();
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
<style scoped>.pairing-steps { display: flex; margin: 6px 0 28px; border: 1px solid var(--line); border-radius: 18px; background: var(--surface); }.step { display: flex; align-items: center; flex: 1; gap: 9px; padding: 18px; color: var(--text-secondary); font-size: 12px; }.step + .step { border-left: 1px solid var(--line); }.step-number { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: var(--surface-soft); border-radius: 9px; font-size: 10px; font-weight: 800; }.step.complete .step-number { background: var(--accent); color: white; }.scan-illustration { display: flex; justify-content: center; padding: 10px 0 24px; }.scan-corners { position: relative; width: 130px; height: 130px; display: flex; align-items: center; justify-content: center; border: 1px dashed #98b18b; border-radius: 24px; background: rgba(255,255,255,.5); overflow: hidden; }.scan-sweep { position: absolute; left: 15px; right: 15px; height: 2px; background: #9bb78e; box-shadow: 0 0 18px #9bb78e; animation: scan-move 3s ease-in-out infinite; }@keyframes scan-move { 0%,100% { transform: translateY(-38px); opacity: .1; }50% { transform: translateY(38px); opacity: .8; } }.scan-browser-tip { text-align: center; }.manual-pairing { margin-top: 22px; padding-top: 22px; border-top: 1px solid #c6d7bf; }.confirm-code { text-align: center; padding: 24px 0; font-size: clamp(28px,5vw,44px); font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: .18em; color: var(--violet); }.confirm-check { display: flex; align-items: center; gap: 8px; width: 100%; min-height: 48px; padding: 8px 0; border: 0; background: transparent; text-align: left; color: var(--text); font-size: 12px; }.confirm-check::after,.agent-option::after { display: none; }.agent-option { display: flex; align-items: center; gap: 12px; width: 100%; padding: 14px 0; border: 0; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }.agent-option .checkbox { margin: 0; }.pairing-status-note { margin-top: 16px; }.technical-info { margin-top: 10px; }@media(max-width:767px){.step { padding: 12px 7px; flex-direction: column; font-size: 10px; gap: 7px; }}</style>
