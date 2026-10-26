// 生成 tabBar 线性图标 PNG(81×81,3×3 超采样抗锯齿)。
// 图标几何与 docs/ui-redesign/prototype.html 的 24×24 线性图标体系一致。
// 用法:node scripts/gen-tabbar-icons.mjs
import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'static', 'tab');
const SIZE = 81; // uni-app tabBar 推荐尺寸
const VIEW = 24; // 图标坐标系
const HALF_W = 0.95; // 描边半宽(线宽 1.9/24,小尺寸下保证可读)
const SS = 3; // 每像素超采样数(每轴)

/* ---------------- PNG 编码(纯 zlib,无第三方依赖) ---------------- */
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}
function pngEncode(width, height, rgba) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  const raw = Buffer.alloc(height * (1 + width * 4));
  for (let y = 0; y < height; y++) {
    raw[y * (1 + width * 4)] = 0; // filter: none
    rgba.copy(raw, y * (1 + width * 4) + 1, y * width * 4, (y + 1) * width * 4);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/* ---------------- SDF 图元(24×24 坐标系,y 向下) ---------------- */
function sdSegment(px, py, ax, ay, bx, by) {
  const abx = bx - ax, aby = by - ay;
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)));
  return Math.hypot(px - (ax + abx * t), py - (ay + aby * t));
}
// 圆弧:角度单位弧度;y 向下坐标系中角度以 +x 为 0、顺时针为正。
// 弧从 a0 扫到 a1,方向由 a1-a0 的符号决定,跨度按最短路径归一到 [-π, π]。
function sdArc(px, py, cx, cy, r, a0, a1) {
  const dx = px - cx, dy = py - cy;
  const ang = Math.atan2(dy, dx);
  const TAU = Math.PI * 2;
  let span = a1 - a0;
  if (span > Math.PI) span -= TAU;
  if (span < -Math.PI) span += TAU;
  let rel = ((ang - a0 + Math.PI) % TAU + TAU) % TAU - Math.PI;
  const onArc = span >= 0 ? rel >= 0 && rel <= span : rel <= 0 && rel >= span;
  if (onArc) return Math.abs(Math.hypot(dx, dy) - r);
  const p0 = [cx + r * Math.cos(a0), cy + r * Math.sin(a0)];
  const p1 = [cx + r * Math.cos(a1), cy + r * Math.sin(a1)];
  return Math.min(sdSegment(px, py, p0[0], p0[1], p1[0], p1[1]));
}
function sdRectOutline(px, py, x0, y0, x1, y1, r) {
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const hx = (x1 - x0) / 2 - r, hy = (y1 - y0) / 2 - r;
  const qx = Math.abs(px - cx) - hx, qy = Math.abs(py - cy) - hy;
  const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0));
  const inside = Math.min(Math.max(qx, qy), 0);
  return Math.abs(outside + inside - r);
}
function sdCircleOutline(px, py, cx, cy, r) {
  return Math.abs(Math.hypot(px - cx, py - cy) - r);
}

/* ---------------- 三个图标(与模板 data-icon 路径一致的几何) ---------------- */
// 会话:圆角气泡 + 左下尾巴 + 两条文本线
function iconChat(x, y) {
  return Math.min(
    sdRectOutline(x, y, 4, 4, 20, 17, 2.5),
    sdSegment(x, y, 9, 17, 4.4, 21),
    sdSegment(x, y, 4.4, 21, 4, 18),
    sdSegment(x, y, 8, 9.5, 16, 9.5),
    sdSegment(x, y, 8, 13, 13, 13),
  );
}
// 联系人:两个人(大人 + 右后小人)
function iconContacts(x, y) {
  const p1Head = sdCircleOutline(x, y, 9, 7.5, 3.6);
  const p1Body = Math.min(
    sdSegment(x, y, 15, 21, 15, 19),
    sdArc(x, y, 11, 19, 4, 0, -Math.PI / 2),
    sdSegment(x, y, 11, 15, 7, 15),
    sdArc(x, y, 7, 19, 4, -Math.PI / 2, Math.PI),
    sdSegment(x, y, 3, 19, 3, 21),
  );
  const p2Head = sdArc(x, y, 17.2, 7.5, 3.1, -Math.PI / 2.4, Math.PI / 2.4);
  const p2Body = sdArc(x, y, 14.8, 20.4, 4.4, -Math.PI / 2.2, 0.5);
  return Math.min(p1Head, p1Body, p2Head, p2Body);
}
// 我的:头像 + 肩部圆弧
function iconUser(x, y) {
  return Math.min(
    sdCircleOutline(x, y, 12, 8, 4),
    sdArc(x, y, 12, 21, 8, Math.PI, Math.PI * 2),
  );
}

const ICONS = { chat: iconChat, contacts: iconContacts, user: iconUser };
const COLORS = {
  normal: [0x60, 0x6d, 0x63], // --text-secondary
  active: [0x21, 0x6a, 0x50], // --accent
};

function rasterize(sdf, [r, g, b]) {
  const rgba = Buffer.alloc(SIZE * SIZE * 4);
  const step = VIEW / SIZE;
  for (let py = 0; py < SIZE; py++) {
    for (let px = 0; px < SIZE; px++) {
      let cov = 0;
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const x = (px + (sx + 0.5) / SS) * step;
          const y = (py + (sy + 0.5) / SS) * step;
          if (sdf(x, y) < HALF_W) cov += 1 / (SS * SS);
        }
      }
      const i = (py * SIZE + px) * 4;
      rgba[i] = r; rgba[i + 1] = g; rgba[i + 2] = b;
      rgba[i + 3] = Math.round(cov * 255);
    }
  }
  return rgba;
}

mkdirSync(OUT_DIR, { recursive: true });
for (const [name, sdf] of Object.entries(ICONS)) {
  for (const [variant, color] of Object.entries(COLORS)) {
    const file = join(OUT_DIR, `${name}${variant === 'active' ? '-active' : ''}.png`);
    writeFileSync(file, pngEncode(SIZE, SIZE, rasterize(sdf, color)));
    console.log('written', file);
  }
}
