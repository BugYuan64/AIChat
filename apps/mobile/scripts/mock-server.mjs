// 本地 mock API:给 H5 预览提供假数据(不写库、无鉴权,仅开发用)。
// 用法:node scripts/mock-server.mjs  (监听 127.0.0.1:8000,与客户端默认 serverBase 一致)
import { createServer } from 'node:http';

const now = () => new Date().toISOString();
const ts = (h, m) => `2026-10-27T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+08:00`;

const ME = { account_id: 'acc_me', kind: 'human', handle: 'linjian', display_name: '林间', bio: '保持好奇,慢慢做好。', status: 'active' };
const CHEN = { account_id: 'acc_chen', kind: 'human', handle: 'chenyi', display_name: '陈一', status: 'active' };
const SUMMARY = { account_id: 'acc_ai', kind: 'ai', handle: 'summary', display_name: '归纳助手', bio: '把散落的想法整理成清晰的结论。', status: 'active' };

const conversations = [
  {
    conversation_id: 'conv_group', kind: 'group', title: '周末项目组', unread_count: 2, updated_at: ts(14, 32),
    last_message: { seq: '42', sender_account_id: 'acc_ai', kind: 'text', text: '好的,我们从最重要的问题开始。', created_at: ts(14, 32) },
  },
  {
    conversation_id: 'conv_ai', kind: 'direct', title: '归纳助手', unread_count: 0, updated_at: ts(13, 48),
    direct_peer: { account_id: 'acc_ai', kind: 'ai', handle: 'summary', display_name: '归纳助手' },
    last_message: { seq: '18', sender_account_id: 'acc_ai', kind: 'text', text: '好的,我们从最重要的问题开始。', created_at: ts(13, 48) },
  },
  {
    conversation_id: 'conv_human', kind: 'direct', title: '陈一', unread_count: 0, updated_at: ts(9, 12),
    direct_peer: { account_id: 'acc_chen', kind: 'human', handle: 'chenyi', display_name: '陈一' },
    last_message: { seq: '9', sender_account_id: 'acc_chen', kind: 'text', text: '周六一起把原型过一遍?', created_at: ts(9, 12) },
  },
];

const members = {
  conv_group: [
    { membership_id: 'm1', conversation_id: 'conv_group', account_id: 'acc_me', role: 'owner', joined_seq: '1', account: ME },
    { membership_id: 'm2', conversation_id: 'conv_group', account_id: 'acc_chen', role: 'member', joined_seq: '2', account: CHEN },
    { membership_id: 'm3', conversation_id: 'conv_group', account_id: 'acc_ai', role: 'member', joined_seq: '3', account: SUMMARY },
  ],
  conv_ai: [
    { membership_id: 'm4', conversation_id: 'conv_ai', account_id: 'acc_me', role: 'owner', joined_seq: '1', account: ME },
    { membership_id: 'm5', conversation_id: 'conv_ai', account_id: 'acc_ai', role: 'member', joined_seq: '1', account: SUMMARY },
  ],
  conv_human: [
    { membership_id: 'm6', conversation_id: 'conv_human', account_id: 'acc_me', role: 'owner', joined_seq: '1', account: ME },
    { membership_id: 'm7', conversation_id: 'conv_human', account_id: 'acc_chen', role: 'member', joined_seq: '1', account: CHEN },
  ],
};

const messages = {
  conv_group: [
    { message_id: 'msg_sys', conversation_id: 'conv_group', seq: '40', sender_account_id: 'acc_chen', kind: 'system', text: '陈一 邀请 归纳助手 加入了群聊', mentions: [], status: 'final', revision: '1', created_at: ts(14, 20), updated_at: ts(14, 20) },
    { message_id: 'msg_1', conversation_id: 'conv_group', seq: '41', sender_account_id: 'acc_chen', kind: 'text', text: '我们先把首版最重要的体验做好,其他功能可以慢慢来。', mentions: [], status: 'final', revision: '1', created_at: ts(14, 28), updated_at: ts(14, 28) },
    { message_id: 'msg_2', conversation_id: 'conv_group', seq: '42', sender_account_id: 'acc_me', kind: 'text', text: '@归纳助手 帮我们把刚才的讨论整理一下,重点放在下一步要做什么。', mentions: ['acc_ai'], status: 'final', revision: '1', created_at: ts(14, 30), updated_at: ts(14, 30) },
    {
      message_id: 'msg_3', conversation_id: 'conv_group', seq: '43', sender_account_id: 'acc_ai', kind: 'text', run_id: 'run_1', trigger_message_id: 'msg_2',
      text: '可以。我们先围绕一个目标推进:让每一段对话都更容易开始,也更容易继续。\n\n1. 先理清信息,一眼能看到谁在说话、讨论到哪里。\n2. 把重要操作放近一点:发消息、选择 AI、停止生成。\n3. 让状态更明确:已发送、正在处理、等待确认,各自说清楚。',
      mentions: [], status: 'final', revision: '1', created_at: ts(14, 32), updated_at: ts(14, 33),
    },
    { message_id: 'msg_4', conversation_id: 'conv_group', seq: '44', sender_account_id: 'acc_chen', kind: 'text', text: '同意,那就按这个顺序推进。', mentions: [], status: 'final', revision: '1', reply_to_message_id: 'msg_1', created_at: ts(14, 35), updated_at: ts(14, 35) },
  ],
  conv_ai: [
    { message_id: 'msg_a1', conversation_id: 'conv_ai', seq: '17', sender_account_id: 'acc_ai', kind: 'text', text: '你好。把你的想法发给我,我们一起理清思路。', mentions: [], status: 'final', revision: '1', created_at: ts(13, 40), updated_at: ts(13, 40) },
    { message_id: 'msg_a2', conversation_id: 'conv_ai', seq: '18', sender_account_id: 'acc_me', kind: 'text', text: '我在整理这周的项目笔记,等下发你。', mentions: [], status: 'final', revision: '1', created_at: ts(13, 48), updated_at: ts(13, 48) },
  ],
  conv_human: [
    { message_id: 'msg_h1', conversation_id: 'conv_human', seq: '9', sender_account_id: 'acc_chen', kind: 'text', text: '周六一起把原型过一遍?', mentions: [], status: 'final', revision: '1', created_at: ts(9, 12), updated_at: ts(9, 12) },
  ],
};

const runs = {
  run_1: {
    run_id: 'run_1', conversation_id: 'conv_group', agent_id: 'acc_ai', trigger_message_id: 'msg_2', reply_message_id: 'msg_3',
    state: 'running', attempt_no: 1, binding_generation: 3, created_at: ts(14, 30), started_at: ts(14, 31), updated_at: ts(14, 33),
  },
};

const agents = [
  {
    agent_id: 'acc_ai', owner_account_id: 'acc_me', handle: 'summary', display_name: '归纳助手', bio: '把散落的想法整理成清晰的结论。', status: 'active', online: true,
    binding: { mode: 'model_api', provider_code: 'openai', model_name: 'gpt-4o-mini', generation: 3, enabled: true }, grants: [],
  },
  {
    agent_id: 'acc_ai2', owner_account_id: 'acc_me', handle: 'research', display_name: '研究搭档', bio: '连接你自己的设备,在熟悉的环境里处理任务。', status: 'active', online: false,
    binding: { mode: 'connector', generation: 1, enabled: false }, grants: [],
  },
];

const contacts = {
  items: [
    { account: CHEN, relation: 'connected' },
    { account: { account_id: 'acc_ai', kind: 'ai', handle: 'summary', display_name: '归纳助手' }, relation: 'connected' },
    { account: { account_id: 'acc_wang', kind: 'human', handle: 'wangwu', display_name: '王五' }, relation: 'pending_incoming', request_id: 'req_1' },
    { account: { account_id: 'acc_zhao', kind: 'human', handle: 'zhaoliu', display_name: '赵六' }, relation: 'pending_outgoing' },
  ],
};

const sessions = {
  items: [
    { session_id: 's1', device_summary: 'Chrome 141 · Windows', created_at: '2026-10-20T09:00:00+08:00', expires_at: '2026-11-20T09:00:00+08:00', current: true },
    { session_id: 's2', device_summary: 'Android · AIChat App', created_at: '2026-10-25T21:30:00+08:00', expires_at: '2026-11-25T21:30:00+08:00', current: false },
  ],
};

createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:8000');
  const p = url.pathname;
  // H5 预览跨域:放行任意来源(仅本地 mock)
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization,Content-Type');
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }
  const send = (data) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ request_id: 'mock-req', data }));
  };
  console.log(req.method, p);

  if (p === '/v1/conversations') return send({ items: conversations });
  const convMatch = /^\/v1\/conversations\/([^/]+)(\/.*)?$/.exec(p);
  if (convMatch) {
    const id = decodeURIComponent(convMatch[1]);
    const sub = convMatch[2];
    if (!sub) {
      const conv = conversations.find((c) => c.conversation_id === id);
      return conv ? send({ ...conv, members: members[id] ?? [], my_role: 'owner' }) : notFound();
    }
    if (sub === '/messages') return send({ items: messages[id] ?? [], has_more: false });
    if (sub === '/read') return send({});
  }
  if (p === '/v1/contacts') return send({ items: [CHEN, { account_id: 'acc_ai', kind: 'ai', handle: 'summary', display_name: '归纳助手' }] });
  if (p === '/v1/contact-requests') {
    return send({
      items: [
        { request_id: 'req_1', direction: 'incoming', requester_account_id: 'acc_wang', account: { account_id: 'acc_wang', kind: 'human', handle: 'wangwu', display_name: '王五' } },
        { request_id: 'req_2', direction: 'outgoing', requester_account_id: 'acc_zhao', account: { account_id: 'acc_zhao', kind: 'human', handle: 'zhaoliu', display_name: '赵六' } },
      ],
    });
  }
  if (p === '/v1/me') return send(ME);
  if (p === '/v1/sessions') return send(sessions);
  if (p === '/v1/agents') return send({ items: agents });
  const agentMatch = /^\/v1\/agents\/([^/]+)(\/.*)?$/.exec(p);
  if (agentMatch) {
    const id = decodeURIComponent(agentMatch[1]);
    const sub = agentMatch[2];
    const agent = agents.find((a) => a.agent_id === id);
    if (!sub) return agent ? send(agent) : notFound();
    if (sub === '/grants') return send({ items: [] });
    if (sub === '/connectors') return send({ items: [{ connector_id: 'c1', agent_id: id, name: '书房电脑', platform: 'linux', online: true, created_at: '2026-10-24T10:00:00+08:00' }] });
  }
  if (p === '/v1/events') return send({ items: [], next_cursor: '100', has_more: false });
  if (p === '/v1/realtime-tickets') return send({ ticket: 'mock-ticket', expires_in: 30 });
  const runMatch = /^\/v1\/runs\/([^/]+)$/.exec(p);
  if (runMatch) {
    const run = runs[decodeURIComponent(runMatch[1])];
    return run ? send(run) : notFound();
  }
  if (p.startsWith('/v1/accounts/by-handle')) {
    const handle = url.searchParams.get('handle');
    const all = [ME, CHEN, SUMMARY];
    const acc = all.find((a) => a.handle === handle);
    return acc ? send(acc) : notFound();
  }
  return send({});

  function notFound() {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ request_id: 'mock-req', error: { code: 'NOT_FOUND', message: 'mock 未实现', retryable: false } }));
  }
}).listen(8000, '127.0.0.1', () => console.log('mock api on 127.0.0.1:8000'));
