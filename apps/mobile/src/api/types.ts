/**
 * 与 contracts/PROTOCOL.md 字段一一对应的 TypeScript 类型。
 *
 * 约定（PROTOCOL.md §0）：
 * - ID 为不透明字符串；时间为 UTC RFC3339；
 * - seq / cursor / revision 等大数一律以「十进制字符串」表示，此处全部定义为 string；
 * - 成功/错误信封：{"request_id": "...", "data": {...}} / {"request_id": "...", "error": {...}}。
 */

/* ---------------- 通用信封与错误 ---------------- */

/** 错误信封中的 error 对象（PROTOCOL.md §0） */
export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
  retry_after_ms?: number;
}

/** 成功信封 */
export interface ApiSuccessEnvelope<T> {
  request_id: string;
  data: T;
}

/** 错误信封 */
export interface ApiErrorEnvelope {
  request_id: string;
  error: ApiErrorBody;
}

export type ApiEnvelope<T> = ApiSuccessEnvelope<T> | ApiErrorEnvelope;

/* ---------------- 账号与认证（§1） ---------------- */

export type AccountKind = 'human' | 'ai';

/** account 对象：{account_id, kind, handle, display_name, avatar_url?, bio?, status} */
export interface Account {
  account_id: string;
  kind: AccountKind;
  handle: string;
  display_name: string;
  avatar_url?: string;
  bio?: string;
  /** 规约未枚举取值，按不透明字符串处理 */
  status: string;
}

/** 有限资料（GET /v1/accounts/by-handle 返回，字段可能不全） */
export interface AccountBrief {
  account_id: string;
  handle: string;
  kind: AccountKind;
  display_name?: string;
  avatar_url?: string;
  bio?: string;
}

/** 登录/刷新响应：access_token、refresh_token、expires_in、account */
export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  /** 秒 */
  expires_in: number;
  account: Account;
}

/** POST /v1/realtime-tickets（audience=human_events）响应 */
export interface RealtimeTicket {
  ticket: string;
  /** 秒（默认 30，一次性，连接后首帧提交） */
  expires_in: number;
}

/** GET /v1/sessions 的 items 元素：登录设备会话 */
export interface LoginSession {
  session_id: string;
  device_summary?: string;
  created_at: string;
  last_seen_at?: string;
  expires_at: string;
  /** 是否为当前请求所用会话 */
  current: boolean;
}

/** PATCH /v1/me 载荷（字段均可选，仅更新提供者） */
export interface ProfilePatch {
  display_name?: string;
  avatar_url?: string;
  bio?: string;
}

/* ---------------- 联系人（§2） ---------------- */

/** 关系值以服务端实现为准；pending_* 用于驱动“待处理申请”列表 */
export type ContactRelation = 'connected' | 'pending_incoming' | 'pending_outgoing' | 'blocked';

/** GET /v1/contacts 的 items 元素：account + 关系 */
export interface ContactItem {
  account: AccountBrief;
  relation: ContactRelation;
  /** pending_incoming 时用于 POST /v1/contact-requests/{id}/decision */
  request_id?: string;
}

/* ---------------- 会话与成员（§3） ---------------- */

export type ConversationKind = 'direct' | 'group';
export type MemberRole = 'member' | 'admin' | 'owner';

/** membership 对象：{membership_id, conversation_id, account_id, role, joined_seq, left_seq?} */
export interface Membership {
  membership_id: string;
  conversation_id: string;
  account_id: string;
  role: MemberRole;
  /** 大数十进制字符串 */
  joined_seq: string;
  left_seq?: string;
}

/** 会话详情里的成员（membership + 账号资料，便于渲染） */
export interface ConversationMember extends Membership {
  account: AccountBrief;
}

/** GET /v1/conversations 列表项（信封字段名以服务端实现为准，规约锁定的是路径与内容范围） */
export interface ConversationItem {
  conversation_id: string;
  kind: ConversationKind;
  /** 群聊为群名；私聊为对方昵称（服务端推导） */
  title: string;
  /** 私聊对方 */
  direct_peer?: AccountBrief;
  last_message?: {
    /** 大数十进制字符串 */
    seq: string;
    sender_account_id: string;
    kind: MessageKind;
    text: string;
    created_at: string;
  };
  unread_count?: number;
  updated_at?: string;
  /** 会话已解散/关闭（conversation.closed 事件后为 true） */
  closed?: boolean;
}

/** GET /v1/conversations/{id} 详情 + 当前成员/角色 */
export interface ConversationDetail {
  conversation_id: string;
  kind: ConversationKind;
  title: string;
  members: ConversationMember[];
  /** 大数十进制字符串 */
  permission_version?: string;
  /** 客户端冗余字段（可由 members 推导），服务端有则优先 */
  my_role?: MemberRole;
  closed?: boolean;
}

/** 创建会话（direct/groups）返回的最小引用 */
export interface ConversationRef {
  conversation_id: string;
  kind: ConversationKind;
  title?: string;
}

/** 群邀请（§3；响应信封字段以服务端实现为准） */
export interface Invitation {
  invitation_id: string;
  conversation_id: string;
  invitee_account_id: string;
  inviter_account_id: string;
  status: string;
  created_at?: string;
}

/* ---------------- 消息（§4） ---------------- */

export type MessageKind = 'text' | 'system';
/** AI 回复消息状态流转：draft → partial → final */
export type MessageStatus = 'draft' | 'partial' | 'final';

/**
 * message 对象：
 * {message_id, conversation_id, seq, sender_account_id, kind, text, mentions,
 *  client_message_id?, reply_to_message_id?, run_id?, trigger_message_id?,
 *  status, terminal_reason?, revision, created_at, updated_at}
 */
export interface Message {
  message_id: string;
  conversation_id: string;
  /** 大数十进制字符串，会话内单调 */
  seq: string;
  sender_account_id: string;
  kind: MessageKind;
  text: string;
  /** 被提及成员的账号 ID 列表 */
  mentions: string[];
  client_message_id?: string;
  reply_to_message_id?: string;
  run_id?: string;
  trigger_message_id?: string;
  status: MessageStatus;
  terminal_reason?: string;
  /** 大数十进制字符串，修订号单调递增，客户端按其合并更新 */
  revision: string;
  created_at: string;
  updated_at: string;
}

/** POST /v1/conversations/{id}/messages 请求体 */
export interface SendMessagePayload {
  /** 幂等键：conversation_id + sender + client_message_id；失败重试沿用同一值 */
  client_message_id: string;
  text: string;
  mentions?: string[];
  reply_to_message_id?: string;
}

/** POST .../messages 成功 data：{message, runs[]}（runs 可缺省） */
export interface SendMessageResult {
  message: Message;
  runs?: Run[];
}

/** GET .../messages 分页结果（按 seq 升序，仅可见区间） */
export interface MessagePage {
  items: Message[];
  has_more: boolean;
}

/* ---------------- 事件与实时（§5） ---------------- */

/** 持久事件类型 */
export type PersistentEventType =
  | 'message.created'
  | 'message.updated'
  | 'membership.changed'
  | 'conversation.updated'
  | 'conversation.closed'
  | 'run.updated'
  | 'binding.changed';

/** 临时事件（仅 WSS） */
export type EphemeralEventType = 'run.delta' | 'typing' | 'presence';

/** GET /v1/events 的 items 元素（与人类 WSS 持久事件帧同构） */
export interface EventItem {
  event_id: string;
  /** 大数十进制字符串，单调 */
  cursor: string;
  type: string;
  conversation_id?: string;
  seq?: string;
  payload: unknown;
  occurred_at: string;
}

/** GET /v1/events 响应 data */
export interface EventPage {
  items: EventItem[];
  next_cursor: string;
  has_more: boolean;
}

/** 人类 WSS welcome 帧 */
export interface WelcomeFrame {
  type: 'welcome';
  current_cursor: string;
  heartbeat_seconds?: number;
}

/** 人类 WSS 持久事件帧（§5.2 第 3 条） */
export interface WsEventFrame extends EventItem {
  protocol_version?: number;
}

/** 临时事件 run.delta 帧（字段名以服务端实现为准：run_id + chunk_index + text） */
export interface RunDeltaFrame {
  type: 'run.delta';
  run_id: string;
  message_id?: string;
  conversation_id?: string;
  chunk_index: number;
  text: string;
}

/* ---------------- AI 与绑定（§6） ---------------- */

/** 运行绑定状态（脱敏：不含凭据） */
export interface AgentBinding {
  /** model_api：后端直连模型 API；connector：外部连接器 */
  mode: 'model_api' | 'connector';
  provider_code?: string;
  model_name?: string;
  /** 绑定代际，撤销/重绑 +1 */
  generation: number;
  enabled: boolean;
}

/** CLI agent 执行权限：决定连接器以何种权限运行（对应 CLI 的 --mode） */
export type PermissionMode = 'plan' | 'edit' | 'build' | 'yolo' | 'guarded';

export interface AgentPolicy {
  permission_mode: PermissionMode;
  workspace_dir: string | null;
}

/** AI 使用授权 */
export interface AgentGrant {
  grant_id?: string;
  agent_id: string;
  human_account_id: string;
  account?: AccountBrief;
}

/** GET /v1/agents 返回元素：档案 + 绑定状态 + 在线状态（§6） */
export interface Agent {
  agent_id: string;
  owner_account_id: string;
  handle: string;
  display_name: string;
  bio?: string;
  status: string;
  binding?: AgentBinding;
  /** CLI 执行权限（所有者可见） */
  policy?: AgentPolicy | null;
  online?: boolean;
  /** 服务端若在详情中附带授权列表则用于渲染 */
  grants?: AgentGrant[];
}

/** GET /v1/agents/{id}/connectors 元素（所有者视角） */
export interface AgentConnector {
  connector_id: string;
  agent_id: string;
  name: string;
  platform?: string;
  online: boolean;
  created_at?: string;
  last_seen_at?: string;
}

/* ---------------- 配对（§7，移动端只涉及查看/决策/撤销） ---------------- */

export type PairingStatus =
  | 'pending_user'
  | 'pending_local'
  | 'approved'
  | 'redeemed'
  | 'denied'
  | 'expired'
  | 'cancelled';

/** GET /v1/pairings/{id}?code=short_code 响应（已登录人类） */
export interface PairingInfo {
  pairing_id: string;
  agent_id: string;
  agent_display_name: string;
  owner_account_id: string;
  connector_name: string;
  platform: string;
  requested_capabilities: string[];
  /** 6 位数字确认码，供与连接器本机显示核对 */
  confirm_code: string;
  status: PairingStatus;
  /** 乐观并发版本，decision 时回传 */
  version: number;
  expires_at: string;
}

/* ---------------- 运行（§8） ---------------- */

export type RunState =
  | 'queued'
  | 'dispatched'
  | 'running'
  | 'cancel_requested'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | 'recovery_required';

/**
 * Run 对象（§8 只锁定状态机与接口，字段名以服务端实现为准，
 * 此处为客户端展示所需的最小字段集，未知字段可忽略）。
 */
export interface Run {
  run_id: string;
  conversation_id: string;
  agent_id: string;
  trigger_message_id: string;
  reply_message_id?: string;
  state: RunState;
  attempt_no?: number;
  binding_generation?: number;
  error_code?: string;
  /** 脱敏失败信息 */
  error_message?: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
}
