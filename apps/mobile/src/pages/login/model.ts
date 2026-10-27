export type AuthMode = 'login' | 'register';

export interface AuthFormInput {
  mode: AuthMode;
  handle: string;
  password: string;
  inviteCode: string;
  displayName: string;
}

export type AuthFieldErrors = Partial<Record<'inviteCode' | 'handle' | 'displayName' | 'password', string>>;

export function validateAuthForm(input: AuthFormInput): AuthFieldErrors {
  const errors: AuthFieldErrors = {};
  if (input.mode === 'register' && !input.inviteCode.trim()) errors.inviteCode = '请输入邀请码';
  if (!input.handle.trim()) errors.handle = input.mode === 'login' ? '请输入账号名' : '请设置账号名';
  if (input.mode === 'register' && !input.displayName.trim()) errors.displayName = '请输入昵称';
  if (!input.password) errors.password = input.mode === 'login' ? '请输入密码' : '请设置密码';
  return errors;
}

export function loginCopy(mode: AuthMode) {
  return mode === 'login'
    ? {
        title: '登录 AIChat',
        heading: '欢迎回来',
        accountPlaceholder: '请输入账号名',
        passwordAutocomplete: 'current-password',
      }
    : {
        title: '邀请注册 AIChat',
        heading: '使用邀请加入',
        accountPlaceholder: '设置唯一账号名',
        passwordAutocomplete: 'new-password',
      };
}

export function normalizeServerOrigin(value: string): string {
  const input = value.trim();
  if (!input) throw new Error('请输入服务器地址');
  if (!/^[a-z][a-z\d+.-]*:\/\//i.test(input)) throw new Error('请补充 http:// 或 https:// 协议');
  if (/^https?:\/\/$/i.test(input)) throw new Error('服务器地址缺少主机名');

  const match = /^([a-z][a-z\d+.-]*):\/\/([^/?#]*)(.*)$/i.exec(input)!;
  const protocol = match[1].toLowerCase();
  const authority = match[2];
  const suffix = match[3];
  if (protocol !== 'http' && protocol !== 'https') throw new Error('仅支持 http:// 或 https:// 协议');
  if (!authority) throw new Error('服务器地址缺少主机名');
  if (authority.includes('@')) throw new Error('服务器地址不能包含用户名或密码');
  if (/[?#]/.test(suffix)) throw new Error('服务器地址不能包含查询参数或片段');
  if (suffix && suffix !== '/') throw new Error('服务器地址只能填写域名或 IP，不要包含路径');
  const host = /^(\[[\da-f:.]+\]|[a-z\d](?:[a-z\d.-]*[a-z\d])?)(?::(\d{1,5}))?$/i.exec(authority);
  if (!host || (host[2] && (Number(host[2]) < 1 || Number(host[2]) > 65535))) throw new Error('服务器地址格式不正确');
  const port = host[2] && !((protocol === 'http' && Number(host[2]) === 80) || (protocol === 'https' && Number(host[2]) === 443)) ? ':' + Number(host[2]) : '';
  return protocol + '://' + host[1].toLowerCase() + port;
}
