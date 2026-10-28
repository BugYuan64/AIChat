<template>
  <PageLayout :title="agent?.display_name || 'AI 详情'" eyebrow="AI PROFILE" subtitle="管理这位搭档的身份、运行方式与访问权限。" active="agents" back :back-fallback="backFallback">
    <InlineNotice v-if="loadError" tone="danger">{{ loadError }}<UiButton variant="ghost" size="small" @click="load">重新加载</UiButton></InlineNotice>
    <view v-else-if="!agent" class="panel-hint">正在加载 AI 档案…</view>
    <view v-if="agent" class="detail-grid">
      <view class="panel-stack">
        <SectionPanel tone="mint">
          <view class="hero-row"><AccountAvatar :name="agent.display_name" kind="agent" size="large" /><view class="data-copy"><text class="hero-name">{{ agent.display_name }}</text><text class="data-description">@{{ agent.handle }}</text></view><UiButton variant="secondary" size="small" icon="square-pen" @click="openEdit">编辑</UiButton></view>
          <view class="button-row"><StatusBadge :tone="agent.online ? 'success' : 'neutral'" :pulse="agent.online">{{ agent.online ? '在线' : '离线' }}</StatusBadge><StatusBadge :tone="agent.status === 'active' ? 'primary' : 'warning'">{{ agent.status === 'active' ? '正常' : '已停用' }}</StatusBadge></view>
          <text v-if="agent.bio" class="agent-bio">{{ agent.bio }}</text>
        </SectionPanel>
        <SectionPanel title="运行方式" description="模型 API 或连接器，同一时间仅启用一种。" icon="bot">
          <view v-if="agent.binding?.enabled" class="binding-summary">
            <view class="data-row"><view class="binding-symbol"><UiIcon :name="agent.binding.mode === 'model_api' ? 'bot' : 'link-2'" tone="primary" :size="24" /></view><view class="data-copy"><text class="data-title">{{ agent.binding.mode === 'model_api' ? '模型 API' : '外部连接器' }}</text><text class="data-description">{{ agent.binding.mode === 'model_api' ? [agent.binding.provider_code, agent.binding.model_name].filter(Boolean).join(' / ') : '通过已配对设备运行' }}</text></view><StatusBadge tone="primary">已启用</StatusBadge></view>
            <text class="panel-hint">绑定代际 {{ agent.binding.generation }}。凭据由服务器加密保存。</text>
            <view class="button-row"><UiButton variant="danger" size="small" @click="revokeBinding">撤销当前绑定</UiButton></view>
          </view>
          <view v-else><EmptyState icon="link-2" title="选择一种方式，让搭档开始工作" description="使用模型 API 直接接入，或在外部连接器发起配对。" /><view class="binding-choices"><UiButton icon="bot" @click="bindingVisible = true">绑定模型 API</UiButton><UiButton variant="secondary" icon="scan-line" @click="openPairing">配对连接器</UiButton></view></view>
        </SectionPanel>
        <SectionPanel title="执行权限" description="连接器以该权限在主机上运行 CLI。默认只允许读取与规划。" icon="shield-check" :tone="policyMode === 'plan' ? 'mint' : 'danger'">
          <view class="data-row"><view class="data-copy"><text class="data-title">{{ modeLabel(policyMode) }}</text><text class="data-description">{{ modeDescription(policyMode) }}</text></view><StatusBadge :tone="policyMode === 'plan' ? 'success' : policyMode === 'yolo' ? 'danger' : 'warning'">{{ policyMode }}</StatusBadge></view>
          <text class="panel-hint">工作目录：{{ agent.policy?.workspace_dir || '未设置（使用连接器默认目录）' }}</text>
          <InlineNotice v-if="policyMode === 'yolo'" tone="danger" title="当前为完全委托">CLI 将自动批准所有操作，包括文件写入与命令执行，无需再向你确认。</InlineNotice>
          <view class="button-row"><UiButton variant="secondary" size="small" icon="square-pen" @click="openPolicy">调整权限</UiButton></view>
        </SectionPanel>
        <SectionPanel title="使用授权" description="默认只有你可以使用这个 AI，按需授权给其他人。" icon="shield-check">
          <view v-for="g in grants" :key="g.human_account_id" class="data-row"><AccountAvatar :name="g.account?.display_name || g.account?.handle || '?'" size="small" /><view class="data-copy"><text class="data-title">{{ g.account?.display_name || g.account?.handle || g.human_account_id }}</text><text class="data-description">@{{ g.account?.handle || g.human_account_id }}</text></view><UiButton variant="danger" size="small" @click="revokeGrant(g)">撤销</UiButton></view>
          <text v-if="!grants.length" class="panel-hint">目前没有其他被授权用户。</text>
          <view class="grant-form"><input v-model="grantHandle" class="input" aria-label="要授权的用户账号名" placeholder="输入人类用户的账号名" /><UiButton variant="secondary" size="small" @click="addGrant">授权</UiButton></view>
        </SectionPanel>
      </view>
      <view class="panel-stack">
        <SectionPanel title="已连接设备" description="查看与撤销已绑定的连接器。" icon="link-2">
          <EmptyState v-if="!connectors.length" icon="link-2" title="还没有连接器" description="在连接器上发起配对后，使用当前客户端扫码批准。" />
          <view v-for="c in connectors" :key="c.connector_id" class="connector-row"><view class="data-row"><view class="data-copy"><text class="data-title">{{ c.name }}</text><text class="data-description">{{ c.platform || '未知平台' }} · {{ formatTime(c.created_at) }}</text></view><StatusBadge :tone="c.online ? 'success' : 'neutral'">{{ c.online ? '在线' : '离线' }}</StatusBadge></view><UiButton variant="danger" size="small" @click="revokeConnector(c)">撤销设备</UiButton></view>
        </SectionPanel>
        <SectionPanel title="独立身份，清晰边界" tone="violet" icon="info"><text class="panel-hint">AI 使用独立账号参与对话。授权决定谁能触发它，绑定决定它在哪里运行。撤销绑定会取消在途运行。</text></SectionPanel>
      </view>
    </view>
    <template #overlay>
      <BottomSheet :open="policyVisible" title="执行权限" @close="policyVisible = false">
        <view class="sheet-form">
          <InlineNotice v-if="policyError" tone="danger">{{ policyError }}</InlineNotice>
          <text class="panel-hint">权限越高，CLI 能对你主机做的改动越大。不确定时保持「只读规划」。</text>
          <NativeButton v-for="opt in POLICY_OPTIONS" :key="opt.value" class="mode-option" :aria-pressed="policyForm.permission_mode === opt.value" @click="policyForm.permission_mode = opt.value">
            <view class="data-copy"><text class="data-title">{{ opt.label }}</text><text class="data-description">{{ opt.description }}</text></view>
            <view class="radio-dot" :class="{ checked: policyForm.permission_mode === opt.value }"><view v-if="policyForm.permission_mode === opt.value" class="radio-dot-inner" /></view>
          </NativeButton>
          <view class="field"><label class="field-label">工作目录（可选）</label><input v-model="policyForm.workspace_dir" class="input" aria-label="工作目录" placeholder="留空则使用连接器默认目录" /></view>
        </view>
        <template #footer><UiButton class="wide-button" :loading="savingPolicy" @click="savePolicy">{{ savingPolicy ? '正在保存…' : '保存权限设置' }}</UiButton></template>
      </BottomSheet>
      <BottomSheet :open="editVisible" title="编辑 AI 档案" @close="editVisible = false"><view class="sheet-form"><view class="field"><label class="field-label">名称</label><input v-model="editForm.display_name" class="input" aria-label="AI 名称" :maxlength="64" /></view><label class="field-label">账号状态</label><view class="button-row"><UiButton :variant="editForm.status === 'active' ? 'primary' : 'secondary'" @click="editForm.status = 'active'">启用</UiButton><UiButton :variant="editForm.status === 'disabled' ? 'danger' : 'secondary'" @click="editForm.status = 'disabled'">停用</UiButton></view></view><template #footer><UiButton class="wide-button" @click="saveEdit">保存档案</UiButton></template></BottomSheet>
      <BottomSheet :open="bindingVisible" title="绑定模型 API" @close="closeBinding"><view class="sheet-form"><InlineNotice v-if="actionError" tone="danger">{{ actionError }}</InlineNotice><view class="field"><label class="field-label">供应商代码</label><input v-model="bindForm.provider_code" class="input" aria-label="供应商代码" placeholder="管理员预配置的 provider_code" /></view><view class="field"><label class="field-label">模型名称</label><input v-model="bindForm.model_name" class="input" aria-label="模型名称" placeholder="输入供应商支持的模型名" /></view><view class="field"><label class="field-label">API 密钥</label><input v-model="bindForm.credential" class="input" password aria-label="API 密钥" placeholder="仅提交至服务器，不在本地存储" /></view><view class="field"><label class="field-label">系统提示词（可选）</label><textarea v-model="bindForm.system_prompt" class="textarea" aria-label="系统提示词" :maxlength="2000" /></view><text class="panel-hint">连接测试通过后才会启用。密钥由服务器加密保存。</text></view><template #footer><UiButton class="wide-button" :loading="binding" @click="bindModel">{{ binding ? '正在测试连接…' : '测试并启用' }}</UiButton></template></BottomSheet>
    </template>
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

import { computed, ref } from 'vue';
import { onLoad, onShow } from '@dcloudio/uni-app';
import * as agentsApi from '../../api/agents';
import { revokeConnector as revokeConnectorApi } from '../../api/pairing';
import { describeError } from '../../api/client';
import { formatTime } from '../../utils/misc';
import type { BackFallback } from '../../utils/nav';
import type { Agent, AgentConnector, AgentGrant } from '../../api/types';

/** 深链直达时页面栈只有一层，返回键要回到「我的 AI」列表而不是会话页 */
const backFallback: BackFallback = { url: '/pages/agents/agents' };

const agentId = ref('');
const agent = ref<Agent | null>(null);
const loadError = ref('');

const editVisible = ref(false);
const bindingVisible = ref(false);
const actionError = ref('');
const editForm = ref({ display_name: '', status: 'active' });

const binding = ref(false);
const bindForm = ref({ provider_code: '', model_name: '', credential: '', system_prompt: '' });

const grants = computed<AgentGrant[]>(() => agent.value?.grants ?? []);
const grantHandle = ref('');
const connectors = ref<AgentConnector[]>([]);

/** 执行权限：默认 plan，与后端默认一致 */
const policyVisible = ref(false);
const policyError = ref('');
const savingPolicy = ref(false);
const policyForm = ref<{ permission_mode: string; workspace_dir: string }>({ permission_mode: 'plan', workspace_dir: '' });

const POLICY_OPTIONS = [
  { value: 'plan', label: '只读规划', description: '只能阅读与给出方案，不写文件、不执行命令' },
  { value: 'edit', label: '可控写入', description: '可以修改文件；命令执行仍受 CLI 自身约束' },
  { value: 'yolo', label: '完全委托', description: '自动批准一切操作，包括命令执行。谨慎使用' },
] as const;

const policyMode = computed(() => agent.value?.policy?.permission_mode ?? 'plan');

function modeLabel(mode: string): string {
  return POLICY_OPTIONS.find((o) => o.value === mode)?.label ?? mode;
}

function modeDescription(mode: string): string {
  return POLICY_OPTIONS.find((o) => o.value === mode)?.description ?? '';
}

function openPolicy() {
  policyError.value = '';
  policyForm.value = {
    permission_mode: policyMode.value,
    workspace_dir: agent.value?.policy?.workspace_dir ?? '',
  };
  policyVisible.value = true;
}

async function savePolicy() {
  if (savingPolicy.value) return;
  savingPolicy.value = true;
  policyError.value = '';
  try {
    agent.value = await agentsApi.setPolicy(agentId.value, {
      permission_mode: policyForm.value.permission_mode,
      workspace_dir: policyForm.value.workspace_dir.trim() || null,
    });
    policyVisible.value = false;
  } catch (err) {
    policyError.value = describeError(err);
  } finally {
    savingPolicy.value = false;
  }
}

onLoad((options) => {
  agentId.value = options?.id ?? '';
});

onShow(() => {
  if (agentId.value) void load();
});

async function load() {
  try {
    agent.value = await agentsApi.getAgent(agentId.value);
    loadError.value = '';
    const res = await agentsApi.listConnectors(agentId.value);
    const raw = res as unknown;
    connectors.value = Array.isArray(raw) ? (raw as AgentConnector[]) : ((raw as { items?: AgentConnector[] })?.items ?? []);
  } catch (e) {
    loadError.value = describeError(e);
  }
}

/* ---------------- 档案编辑 ---------------- */

function openEdit() {
  editForm.value = {
    display_name: agent.value?.display_name ?? '',
    status: agent.value?.status === 'disabled' ? 'disabled' : 'active',
  };
  editVisible.value = true;
}

async function saveEdit() {
  try {
    agent.value = await agentsApi.updateAgent(agentId.value, {
      display_name: editForm.value.display_name.trim() || undefined,
      status: editForm.value.status,
    });
    editVisible.value = false;
    uni.showToast({ title: '已保存', icon: 'success' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

/* ---------------- 绑定 ---------------- */

async function bindModel() {
  const f = bindForm.value;
  if (!f.provider_code.trim() || !f.model_name.trim() || !f.credential) {
    uni.showToast({ title: '请填写供应商务、模型名与密钥', icon: 'none' });
    return;
  }
  if (binding.value) return;
  binding.value = true;
  actionError.value = '';
  try {
    agent.value = await agentsApi.bindModel(agentId.value, {
      provider_code: f.provider_code.trim(),
      model_name: f.model_name.trim(),
      credential: f.credential,
      system_prompt: f.system_prompt.trim() || undefined,
    });
    bindForm.value = { provider_code: '', model_name: '', credential: '', system_prompt: '' };
    bindingVisible.value = false;
    uni.showToast({ title: '连接测试通过，已启用', icon: 'success' });
  } catch (e) {
    actionError.value = describeError(e);
  } finally {
    binding.value = false;
  }
}

function revokeBinding() {
  uni.showModal({
    title: '撤销绑定',
    content: '将取消在途运行并使代际 +1，确定继续？',
    confirmText: '撤销',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await agentsApi.revokeBinding(agentId.value);
        uni.showToast({ title: '已撤销', icon: 'none' });
        await load();
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

/* ---------------- 授权 ---------------- */

async function addGrant() {
  const h = grantHandle.value.trim();
  if (!h) return;
  try {
    const target = await agentsApi.findHumanByHandle(h);
    await agentsApi.grantUse(agentId.value, target.account_id);
    // 详情接口未返回授权列表时，本地乐观补充一条
    if (!agent.value?.grants?.some((g) => g.human_account_id === target.account_id)) {
      agent.value = {
        ...(agent.value as Agent),
        grants: [...(agent.value?.grants ?? []), { agent_id: agentId.value, human_account_id: target.account_id, account: target }],
      };
    }
    grantHandle.value = '';
    uni.showToast({ title: '已授权', icon: 'success' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
  }
}

function revokeGrant(g: AgentGrant) {
  uni.showModal({
    title: '撤销授权',
    content: `撤销 ${g.account?.display_name || g.account?.handle || '该用户'} 对此 AI 的使用授权？`,
    confirmText: '撤销',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await agentsApi.revokeGrant(agentId.value, g.human_account_id);
        if (agent.value) {
          agent.value = { ...agent.value, grants: (agent.value.grants ?? []).filter((x) => x.human_account_id !== g.human_account_id) };
        }
        uni.showToast({ title: '已撤销', icon: 'none' });
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}

/* ---------------- 连接器 ---------------- */

function revokeConnector(c: AgentConnector) {
  uni.showModal({
    title: '撤销连接器',
    content: `撤销「${c.name}」？其会话将关闭，在途任务取消，代际 +1。`,
    confirmText: '撤销',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await revokeConnectorApi(c.connector_id);
        uni.showToast({ title: '已撤销', icon: 'none' });
        await load();
      } catch (e) {
        uni.showToast({ title: describeError(e), icon: 'none' });
      }
    },
  });
}
function openPairing() { uni.navigateTo({ url: '/pages/pairing/scan' }); }
function closeBinding() { if (binding.value) return; bindingVisible.value = false; bindForm.value.credential = ''; }
</script>
<style scoped>.agent-bio { display: block; margin-top: 20px; color: var(--text-secondary); font-size: 14px; line-height: 1.7; }.binding-symbol { width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--line); border-radius: 16px; background: var(--accent-soft); }.binding-summary > .panel-hint { margin-top: 15px; }.binding-choices { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }.grant-form { display: flex; align-items: center; gap: 10px; margin-top: 18px; }.grant-form > .input { flex: 1; min-width: 0; }.connector-row { padding-bottom: 18px; border-bottom: 1px solid var(--line); }.connector-row:last-child { border-bottom: 0; }.connector-row .data-row { border-bottom: 0; }.sheet-form { padding: 0 22px 22px; }.sheet-form > .inline-notice { margin-bottom: 16px; }.mode-option { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; margin-top: 10px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 16px; background: var(--surface); text-align: left; }.mode-option[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); }.radio-dot { flex: 0 0 20px; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--line); border-radius: 50%; }.radio-dot.checked { border-color: var(--accent); background: var(--accent); }.radio-dot-inner { width: 8px; height: 8px; border-radius: 50%; background: var(--surface); }</style>
