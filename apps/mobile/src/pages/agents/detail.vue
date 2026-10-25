<template>
  <view class="page" v-if="agent">
    <!-- 档案 -->
    <view class="card">
      <view class="profile-row">
        <view class="avatar ai big">{{ (agent.display_name || 'A').slice(0, 1).toUpperCase() }}</view>
        <view class="list-body">
          <view class="profile-name">{{ agent.display_name }}</view>
          <view class="list-sub">@{{ agent.handle }}</view>
          <view class="list-sub">
            <text :class="['tag', agent.online ? 'tag-online' : 'tag-offline']">{{ agent.online ? '在线' : '离线' }}</text>
            <text class="tag">{{ agent.status === 'active' ? '正常' : agent.status }}</text>
          </view>
        </view>
      </view>
      <view v-if="agent.bio" class="bio">{{ agent.bio }}</view>
      <view class="divider" />
      <view v-if="!editVisible" class="btn btn-ghost" @tap="openEdit">编辑档案</view>
      <view v-else>
        <view class="field">
          <view class="field-label">名称</view>
          <input v-model="editForm.display_name" class="input" :maxlength="64" />
        </view>
        <view class="field">
          <view class="field-label">状态</view>
          <view class="status-row">
            <text :class="['status-opt', editForm.status === 'active' ? 'on' : '']" @tap="editForm.status = 'active'">启用</text>
            <text :class="['status-opt', editForm.status === 'disabled' ? 'on' : '']" @tap="editForm.status = 'disabled'">停用</text>
          </view>
        </view>
        <view class="btn btn-primary btn-small" @tap="saveEdit">保存</view>
        <view class="btn btn-small" @tap="editVisible = false">取消</view>
      </view>
    </view>

    <!-- 运行绑定 -->
    <view class="section-title">运行绑定（模型 API / 连接器二选一，仅一个启用）</view>
    <view class="card">
      <view v-if="agent.binding && agent.binding.enabled" class="binding-info">
        <view class="list-title">
          {{ agent.binding.mode === 'model_api' ? '模型 API' : '连接器' }}
          <text class="tag">代际 {{ agent.binding.generation }}</text>
        </view>
        <view v-if="agent.binding.mode === 'model_api'" class="list-sub">
          {{ agent.binding.provider_code }} / {{ agent.binding.model_name }}（凭据已加密保存，不在客户端展示）
        </view>
        <view class="btn btn-danger btn-small" style="margin-top: 20rpx" @tap="revokeBinding">撤销绑定</view>
      </view>
      <view v-else>
        <view class="list-sub" style="margin-bottom: 20rpx">
          {{ agent.binding && !agent.binding.enabled ? '当前绑定未启用，可重新绑定覆盖。' : '尚未绑定。绑定模型 API 需录入密钥，连接测试通过后启用；外部 Agent 请在连接器上发起配对后到「我的-扫码配对」。' }}
        </view>
        <view class="field">
          <view class="field-label">供应商务（provider_code，管理员预配置）</view>
          <input v-model="bindForm.provider_code" class="input" placeholder="例如 openai" />
        </view>
        <view class="field">
          <view class="field-label">模型名（model_name）</view>
          <input v-model="bindForm.model_name" class="input" placeholder="例如 gpt-4o-mini" />
        </view>
        <view class="field">
          <view class="field-label">密钥（credential，仅提交一次，服务端加密保存）</view>
          <input v-model="bindForm.credential" class="input" password placeholder="不会在本地存储" />
        </view>
        <view class="field">
          <view class="field-label">系统提示词（可选）</view>
          <textarea v-model="bindForm.system_prompt" class="textarea" :maxlength="2000" />
        </view>
        <view class="btn btn-primary" :class="{ 'btn-disabled': binding }" @tap="bindModel">
          {{ binding ? '连接测试中…' : '测试并启用绑定' }}
        </view>
      </view>
    </view>

    <!-- 使用授权 -->
    <view class="section-title">使用授权（默认仅所有者本人可用）</view>
    <view class="card">
      <view v-for="g in grants" :key="g.human_account_id" class="grant-row">
        <view class="list-body">
          <view class="list-title">{{ g.account?.display_name || g.account?.handle || g.human_account_id }}</view>
          <view class="list-sub">@{{ g.account?.handle || g.human_account_id }}</view>
        </view>
        <view class="btn btn-danger btn-small" @tap="revokeGrant(g)">撤销</view>
      </view>
      <view v-if="!grants.length" class="list-sub" style="margin-bottom: 16rpx">暂无其他被授权用户</view>
      <view class="grant-add">
        <input v-model="grantHandle" class="input" placeholder="输入要授权的用户账号名（handle）" />
        <view class="btn btn-ghost btn-small" @tap="addGrant">授权</view>
      </view>
    </view>

    <!-- 连接器 -->
    <view class="section-title">已绑定连接器</view>
    <view class="card">
      <view v-if="!connectors.length" class="list-sub">暂无连接器（可在连接器上发起配对，扫码批准）</view>
      <view v-for="c in connectors" :key="c.connector_id" class="grant-row">
        <view class="list-body">
          <view class="list-title">
            {{ c.name }}
            <text :class="['tag', c.online ? 'tag-online' : 'tag-offline']">{{ c.online ? '在线' : '离线' }}</text>
          </view>
          <view class="list-sub">{{ c.platform || '未知平台' }} · 接入于 {{ formatTime(c.created_at) }}</view>
        </view>
        <view class="btn btn-danger btn-small" @tap="revokeConnector(c)">撤销</view>
      </view>
    </view>
  </view>

  <view v-else class="empty">{{ loadError || '加载中…' }}</view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onLoad, onShow } from '@dcloudio/uni-app';
import * as agentsApi from '../../api/agents';
import { revokeConnector as revokeConnectorApi } from '../../api/pairing';
import { describeError } from '../../api/client';
import { formatTime } from '../../utils/misc';
import type { Agent, AgentConnector, AgentGrant } from '../../api/types';

const agentId = ref('');
const agent = ref<Agent | null>(null);
const loadError = ref('');

const editVisible = ref(false);
const editForm = ref({ display_name: '', status: 'active' });

const binding = ref(false);
const bindForm = ref({ provider_code: '', model_name: '', credential: '', system_prompt: '' });

const grants = computed<AgentGrant[]>(() => agent.value?.grants ?? []);
const grantHandle = ref('');
const connectors = ref<AgentConnector[]>([]);

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
  binding.value = true;
  try {
    agent.value = await agentsApi.bindModel(agentId.value, {
      provider_code: f.provider_code.trim(),
      model_name: f.model_name.trim(),
      credential: f.credential,
      system_prompt: f.system_prompt.trim() || undefined,
    });
    bindForm.value = { provider_code: '', model_name: '', credential: '', system_prompt: '' };
    uni.showToast({ title: '连接测试通过，已启用', icon: 'success' });
  } catch (e) {
    uni.showToast({ title: describeError(e), icon: 'none' });
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
</script>

<style lang="scss" scoped>
.profile-row {
  display: flex;
  align-items: center;
}
.avatar.big {
  width: 110rpx;
  height: 110rpx;
  border-radius: 22rpx;
  font-size: 40rpx;
}
.profile-name {
  font-size: 34rpx;
  font-weight: 600;
}
.bio {
  margin-top: 20rpx;
  font-size: 26rpx;
  color: #5b6472;
}
.status-row {
  display: flex;
  gap: 16rpx;
}
.status-opt {
  padding: 12rpx 32rpx;
  border-radius: 12rpx;
  background: #f2f3f5;
  color: #5b6472;
  font-size: 26rpx;
}
.status-opt.on {
  background: #3b82f6;
  color: #ffffff;
}
.binding-info .tag {
  margin-left: 12rpx;
}
.grant-row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f0f1f3;
}
.grant-row:last-of-type {
  border-bottom: none;
}
.grant-add {
  display: flex;
  gap: 16rpx;
  align-items: center;
  margin-top: 16rpx;
  .input {
    flex: 1;
  }
}
</style>
