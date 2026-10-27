import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { icons } from '@iconify-json/lucide';
import { getIconData, iconToSVG } from '@iconify/utils';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const iconRoot = path.join(root, 'src', 'static', 'icons');
const tabRoot = path.join(root, 'src', 'static', 'tab');

const names = [
  'arrow-left', 'bot', 'check', 'chevron-down', 'chevron-right', 'circle-alert',
  'circle-check', 'circle-x', 'clock-3', 'copy', 'ellipsis', 'external-link',
  'file-text', 'info', 'link-2', 'loader-circle', 'lock-keyhole', 'log-out',
  'message-circle', 'message-square-plus', 'panel-left-close', 'panel-left-open',
  'plus', 'refresh-cw', 'scan-line', 'search', 'send', 'server', 'settings-2',
  'shield-check', 'sparkles', 'square-pen', 'triangle-alert', 'user-plus',
  'user-round', 'users', 'wifi', 'wifi-off', 'x',
];

const tones = {
  default: '#1f2a24',
  muted: '#66736a',
  primary: '#196b55',
  success: '#27765a',
  danger: '#b23b38',
  inverse: '#ffffff',
};

function svgFor(name, color, size) {
  const data = getIconData(icons, name);
  if (!data) throw new Error(`Lucide icon not found: ${name}`);
  const rendered = iconToSVG(data, { width: String(size), height: String(size) });
  const body = rendered.body.replaceAll('currentColor', color);
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${rendered.attributes.viewBox}">${body}</svg>`);
}

async function writePng(file, name, color, size) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const output = await sharp(svgFor(name, color, size), { density: 192 })
    .resize(size, size, { fit: 'contain' })
    .png({ compressionLevel: 9, adaptiveFiltering: false, palette: false })
    .toBuffer();
  await fs.writeFile(file, output);
}

for (const [tone, color] of Object.entries(tones)) {
  for (const name of names) {
    await writePng(path.join(iconRoot, tone, `${name}.png`), name, color, 48);
  }
}

const tabs = [['chat', 'message-circle'], ['contacts', 'users'], ['user', 'user-round']];
for (const [file, name] of tabs) {
  await writePng(path.join(tabRoot, `${file}.png`), name, tones.muted, 81);
  await writePng(path.join(tabRoot, `${file}-active.png`), name, tones.primary, 81);
}

console.log(`Generated ${names.length * Object.keys(tones).length + tabs.length * 2} deterministic PNG icons.`);
