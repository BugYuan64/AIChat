// 本地 mock API:给 H5 预览提供假数据(不写库、无鉴权,仅开发用)。
// 用法:node scripts/mock-server.mjs  (监听 127.0.0.1:8000,与客户端默认 serverBase 一致)
import { createServer } from 'node:http';
import { pathToFileURL } from 'node:url';
import { WebSocketServer } from 'ws';

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

const sessions = {
  items: [
    { session_id: 's1', device_summary: 'Chrome 141 · Windows', created_at: '2026-10-20T09:00:00+08:00', expires_at: '2026-11-20T09:00:00+08:00', current: true },
    { session_id: 's2', device_summary: 'Android · AIChat App', created_at: '2026-10-25T21:30:00+08:00', expires_at: '2026-11-25T21:30:00+08:00', current: false },
  ],
};


export function createMockServer() {
  // Every factory gets its own mutable fixtures. Nothing is written to disk.
  const convs = structuredClone(conversations);
  const memberMap = structuredClone(members);
  const messageMap = structuredClone(messages);
  const runMap = structuredClone(runs);
  const agentList = structuredClone(agents);
  const me = structuredClone(ME);
  const loginSessions = structuredClone(sessions.items);
  const people = [structuredClone(CHEN), structuredClone(SUMMARY)];
  let requests = [
    { request_id: 'req_1', direction: 'incoming', account: { account_id: 'acc_wang', kind: 'human', handle: 'wangwu', display_name: '王五' } },
    { request_id: 'req_2', direction: 'outgoing', account: { account_id: 'acc_zhao', kind: 'human', handle: 'zhaoliu', display_name: '赵六' } },
  ];
  const pairings = new Map();
  const idempotent = new Map();
  let scenario = 'normal';
  let serial = 100;
  const nextId = (prefix) => prefix + '_' + (++serial);
  const makePairing = (id) => ({
    pairing_id: id, agent_id: 'acc_ai2', agent_display_name: '研究搭档', owner_account_id: 'acc_me',
    connector_name: '书房工作站', platform: 'Linux', requested_capabilities: ['chat'], confirm_code: '428619',
    status: 'pending_user', version: 1, expires_at: new Date(Date.now() + 15 * 60000).toISOString(),
  });
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const p = url.pathname;
    const method = req.method;
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Authorization,Content-Type');
    if (method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
    const send = (data, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ request_id: 'mock-local', data })); };
    const error = (status = 404, code = 'NOT_FOUND', message = '未实现的本地 mock 路由') => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ request_id: 'mock-local', error: { code, message, retryable: status >= 500 } })); };
    let body = {};
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      try { const chunks = []; for await (const chunk of req) chunks.push(chunk); body = JSON.parse(Buffer.concat(chunks).toString() || '{}'); }
      catch { return error(400, 'VALIDATION_FAILED', '无效的 JSON'); }
    }
    if (p === '/__mock/scenario' && method === 'POST') {
      scenario = body.scenario || 'normal';
      if (body.runState) runMap.run_1.state = body.runState;
      if (body.pairingStatus) {
        const pairing = pairings.get('demo') || makePairing('demo');
        pairing.status = body.pairingStatus;
        pairings.set('demo', pairing);
      }
      return send({ scenario });
    }
    if (scenario === 'error' && ['/v1/conversations', '/v1/contacts', '/v1/agents'].includes(p)) return error(503, 'TEMPORARILY_UNAVAILABLE', '测试加载失败');
    if (p === '/v1/auth/login' && method === 'POST') {
      if (!body.handle || !body.password || body.password === 'wrong') return error(401, 'AUTH_INVALID', '测试凭据错误');
      return send({ access_token: 'mock-access', refresh_token: 'mock-refresh', account: me });
    }
    if (p === '/v1/auth/register' && method === 'POST') return send({ ...me, handle: body.handle, display_name: body.display_name });
    if (p === '/v1/auth/refresh' && method === 'POST') return send({ access_token: 'mock-access', refresh_token: 'mock-refresh' });
    if (p === '/v1/auth/logout' && method === 'POST') return send({ revoked: true });
    if (p === '/v1/me' && method === 'GET') return send(me);
    if (p === '/v1/me' && method === 'PATCH') { Object.assign(me, { display_name: body.display_name, bio: body.bio }); return send(me); }
    if (p === '/v1/sessions' && method === 'GET') return send({ items: loginSessions });
    if (/^\/v1\/sessions\/[^/]+$/.test(p) && method === 'DELETE') { const index = loginSessions.findIndex((s) => s.session_id === p.split('/').pop()); if (index >= 0) loginSessions.splice(index, 1); return send({ revoked: true }); }
    if (p === '/v1/accounts/by-handle' && method === 'GET') { const account = [me, CHEN, SUMMARY, ...requests.map((r) => r.account)].find((a) => a.handle === url.searchParams.get('handle')); return account ? send(account) : error(); }
    if (p === '/v1/contacts' && method === 'GET') return send({ items: scenario === 'empty' ? [] : people });
    if (p === '/v1/contact-requests' && method === 'GET') return send({ items: scenario === 'empty' ? [] : requests });
    if (p === '/v1/contact-requests' && method === 'POST') { const account = [CHEN, SUMMARY].find((a) => a.account_id === body.target_account_id); if (!account) return error(); const request = { request_id: nextId('req'), direction: 'outgoing', account }; requests.push(request); return send(request); }
    const requestMatch = /^\/v1\/contact-requests\/([^/]+)\/decision$/.exec(p);
    if (requestMatch && method === 'POST') { const request = requests.find((r) => r.request_id === requestMatch[1]); if (!request) return error(); if (body.decision === 'accept') people.push(request.account); requests = requests.filter((r) => r !== request); return send({ decision: body.decision }); }
    if (/^\/v1\/contacts\/[^/]+(?:\/block)?$/.test(p) && ['DELETE', 'POST'].includes(method)) { const index = people.findIndex((person) => person.account_id === p.split('/')[3]); if (index >= 0) people.splice(index, 1); return send({ removed: true }); }
    if (p === '/v1/conversations' && method === 'GET') return send({ items: scenario === 'empty' ? [] : convs });
    if (p === '/v1/conversations/direct' && method === 'POST') {
      const found = convs.find((c) => c.direct_peer?.account_id === body.target_account_id);
      if (found) return send(found);
      const peer = people.find((a) => a.account_id === body.target_account_id);
      if (!peer) return error();
      const conv = { conversation_id: nextId('conv'), title: peer.display_name, kind: 'direct', direct_peer: peer, updated_at: now(), unread_count: 0 };
      convs.push(conv); memberMap[conv.conversation_id] = [{ membership_id: nextId('member'), account: me, role: 'member' }, { membership_id: nextId('member'), account: peer, role: 'member' }]; return send(conv);
    }
    if (p === '/v1/groups' && method === 'POST') {
      const conv = { conversation_id: nextId('group'), kind: 'group', title: body.title, unread_count: 0, updated_at: now() };
      convs.push(conv); memberMap[conv.conversation_id] = [{ membership_id: nextId('member'), account: me, role: 'owner' }]; return send(conv);
    }
    const convMatch = /^\/v1\/conversations\/([^/]+)(\/.*)?$/.exec(p);
    if (convMatch) {
      const id = decodeURIComponent(convMatch[1]), sub = convMatch[2];
      const conv = convs.find((c) => c.conversation_id === id);
      if (!conv) return error();
      if (!sub && method === 'GET') return send({ ...conv, members: memberMap[id] || [] });
      if (!sub && method === 'PATCH') { conv.title = body.title; return send(conv); }
      if (!sub && method === 'DELETE') { conv.closed = true; return send(conv); }
      if (sub === '/messages' && method === 'GET') return send({ items: messageMap[id] || [], has_more: false });
      if (sub === '/messages' && method === 'POST') {
        const key = id + ':' + body.client_message_id;
        if (idempotent.has(key)) return send(idempotent.get(key));
        const message = { message_id: nextId('msg'), conversation_id: id, seq: String(++serial), sender_account_id: 'acc_me', kind: 'text', text: body.text, mentions: body.mentions || [], reply_to_message_id: body.reply_to_message_id, status: 'final', revision: '1', created_at: now(), updated_at: now() };
        (messageMap[id] ||= []).push(message); conv.last_message = message; conv.updated_at = now();
        const result = { message, runs: [] }; idempotent.set(key, result); return send(result);
      }
      if (sub === '/read' && method === 'PUT') { conv.unread_count = 0; return send({ through_seq: body.through_seq }); }
      if (sub === '/invitations' && method === 'POST') return send({ items: body.invitee_account_ids.map((id) => ({ invitation_id: nextId('invite'), invitee_account_id: id, status: 'pending' })) });
      const memberMatch = /^\/members\/([^/]+)$/.exec(sub || '');
      if (memberMatch && method === 'PATCH') { const member = memberMap[id].find((m) => m.membership_id === memberMatch[1]); if (!member) return error(); if (body.role === 'owner') memberMap[id].filter((m) => m.role === 'owner').forEach((m) => m.role = 'member'); member.role = body.role; return send(member); }
      if (memberMatch && method === 'DELETE') { memberMap[id] = memberMap[id].filter((m) => m.membership_id !== memberMatch[1]); return send({ removed: true }); }
      return error();
    }
    if (p === '/v1/agents' && method === 'GET') return send({ items: scenario === 'empty' ? [] : agentList });
    if (p === '/v1/agents' && method === 'POST') { const agent = { agent_id: nextId('ai'), owner_account_id: 'acc_me', display_name: body.display_name, handle: body.handle, bio: body.bio, status: 'active', online: false, grants: [] }; agentList.push(agent); return send(agent); }
    const agentMatch = /^\/v1\/agents\/([^/]+)(\/.*)?$/.exec(p);
    if (agentMatch) {
      const agent = agentList.find((a) => a.agent_id === agentMatch[1]), sub = agentMatch[2];
      if (!agent) return error();
      if (!sub && method === 'GET') return send(agent);
      if (!sub && method === 'PATCH') { Object.assign(agent, body); return send(agent); }
      if (sub === '/grants' && method === 'GET') return send({ items: agent.grants || [] });
      if (sub === '/grants' && method === 'POST') { agent.grants.push({ human_account_id: body.human_account_id, handle: 'chenyi', display_name: '陈一' }); return send({ granted: true }); }
      if (sub?.startsWith('/grants/') && method === 'DELETE') { agent.grants = agent.grants.filter((g) => g.human_account_id !== sub.split('/').pop()); return send({ revoked: true }); }
      if (sub === '/connectors' && method === 'GET') return send({ items: agent.agent_id === 'acc_ai2' ? [] : [{ connector_id: 'c1', agent_id: agent.agent_id, name: '书房电脑', platform: 'linux', online: true, created_at: now() }] });
      if (sub === '/model-binding' && method === 'POST') { agent.binding = { mode: 'model_api', provider_code: body.provider_code, model_name: body.model_name, generation: 1, enabled: true }; return send(agent.binding); }
      if (sub === '/binding/revoke' && method === 'POST') { if (agent.binding) agent.binding.enabled = false; return send({ revoked: true }); }
      return error();
    }
    if (/^\/v1\/connectors\/[^/]+\/revoke$/.test(p) && method === 'POST') return send({ revoked: true });
    const pairingMatch = /^\/v1\/pairings\/([^/]+)(\/decision)?$/.exec(p);
    if (pairingMatch) {
      const id = pairingMatch[1];
      if (!pairings.has(id)) pairings.set(id, makePairing(id));
      const pairing = pairings.get(id);
      if (method === 'GET' && !pairingMatch[2]) return send(pairing);
      if (method === 'POST' && pairingMatch[2]) {
        if (body.expected_version !== pairing.version) return error(409, 'VERSION_CONFLICT', '配对状态已更新');
        pairing.status = body.decision === 'approve' ? 'pending_local' : 'denied'; pairing.version++; return send(pairing);
      }
      return error();
    }
    if (p === '/v1/events' && method === 'GET') return send({ items: [], next_cursor: '100', has_more: false });
    if (p === '/v1/realtime-tickets' && method === 'POST') return send({ ticket: 'mock-ticket', expires_in: 30 });
    const runMatch = /^\/v1\/runs\/([^/]+)(\/cancel|\/retry)?$/.exec(p);
    if (runMatch) {
      const run = runMap[runMatch[1]];
      if (!run) return error();
      if (!runMatch[2] && method === 'GET') return send(run);
      if (runMatch[2] === '/cancel' && method === 'POST') { run.state = 'cancel_requested'; run.updated_at = now(); return send(run); }
      if (runMatch[2] === '/retry' && method === 'POST') { const retry = { ...run, run_id: nextId('run'), state: 'queued', attempt_no: (run.attempt_no || 1) + 1, created_at: now(), started_at: undefined, finished_at: undefined }; runMap[retry.run_id] = retry; return send(retry); }
      return error();
    }
    return error();
  });
  const ws = new WebSocketServer({ server, path: '/v1/realtime' });
  ws.on('connection', (socket) => {
    socket.on('message', (raw) => {
      try {
        const frame = JSON.parse(raw.toString());
        if (frame.type === 'ticket') socket.send(JSON.stringify({ type: 'welcome', current_cursor: '100', heartbeat_seconds: 20 }));
        if (frame.type === 'ping') socket.send(JSON.stringify({ type: 'pong' }));
      } catch { socket.close(1003, 'invalid JSON'); }
    });
  });
  server.on('close', () => ws.close());
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.MOCK_PORT || 8000);
  createMockServer().listen(port, '127.0.0.1', () => console.log('mock api on 127.0.0.1:' + port));
}
