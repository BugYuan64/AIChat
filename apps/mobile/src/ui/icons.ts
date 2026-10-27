export const UI_ICON_NAMES = [
  'arrow-left', 'bot', 'check', 'chevron-down', 'chevron-right', 'circle-alert',
  'circle-check', 'circle-x', 'clock-3', 'copy', 'ellipsis', 'external-link',
  'file-text', 'info', 'link-2', 'loader-circle', 'lock-keyhole', 'log-out',
  'message-circle', 'message-square-plus', 'panel-left-close', 'panel-left-open',
  'plus', 'refresh-cw', 'scan-line', 'search', 'send', 'server', 'settings-2',
  'shield-check', 'sparkles', 'square-pen', 'triangle-alert', 'user-plus',
  'user-round', 'users', 'wifi', 'wifi-off', 'x',
] as const;

export const UI_ICON_TONES = ['default', 'muted', 'primary', 'success', 'danger', 'inverse'] as const;

export type UiIconName = (typeof UI_ICON_NAMES)[number];
export type UiIconTone = (typeof UI_ICON_TONES)[number];

export function isUiIconName(value: string): value is UiIconName {
  return (UI_ICON_NAMES as readonly string[]).includes(value);
}

export function iconSource(name: string, tone: UiIconTone = 'default'): string {
  if (!isUiIconName(name)) throw new Error(`Unknown UI icon: ${name}`);
  if (!(UI_ICON_TONES as readonly string[]).includes(tone)) throw new Error(`Unknown UI icon tone: ${tone}`);
  return `/static/icons/${tone}/${name}.png`;
}
