/* eslint-disable */
// Generates the EkamCore brand app icon for iOS + Android with no external deps.
// Concept: a rounded chat bubble (chat) holding a shield (secure) with an AI
// spark inside (LLM) on an indigo→violet gradient — "secure offline AI chat".
//
// Run: node scripts/generate-icons.js
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

// ---------- tiny vec / math helpers ----------
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const clamp01 = v => clamp(v, 0, 1);
const lerp = (a, b, t) => a + (b - a) * t;
const hexToRgb = h => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];
const mixRgb = (a, b, t) => [
  lerp(a[0], b[0], t),
  lerp(a[1], b[1], t),
  lerp(a[2], b[2], t),
];

// ---------- palette (Nebula: indigo→violet, matches BrandLogo) ----------
const BG_TOP = hexToRgb('#A78BFA');
const BG_BOT = hexToRgb('#6366F1');
const SHIELD_TOP = hexToRgb('#8B5CF6');
const SHIELD_BOT = hexToRgb('#6D28D9');
const WHITE = [255, 255, 255];

// ---------- signed distance fields (normalized 0..1 space) ----------
function sdRoundRect(px, py, cx, cy, hx, hy, r) {
  const qx = Math.abs(px - cx) - (hx - r);
  const qy = Math.abs(py - cy) - (hy - r);
  const ox = Math.max(qx, 0);
  const oy = Math.max(qy, 0);
  const outside = Math.hypot(ox, oy);
  const inside = Math.min(Math.max(qx, qy), 0);
  return outside + inside - r;
}

function sdTriangle(px, py, p0, p1, p2) {
  const e0 = [p1[0] - p0[0], p1[1] - p0[1]];
  const e1 = [p2[0] - p1[0], p2[1] - p1[1]];
  const e2 = [p0[0] - p2[0], p0[1] - p2[1]];
  const v0 = [px - p0[0], py - p0[1]];
  const v1 = [px - p1[0], py - p1[1]];
  const v2 = [px - p2[0], py - p2[1]];
  const pq0 = sub(v0, scale(e0, clamp01(dot(v0, e0) / dot(e0, e0))));
  const pq1 = sub(v1, scale(e1, clamp01(dot(v1, e1) / dot(e1, e1))));
  const pq2 = sub(v2, scale(e2, clamp01(dot(v2, e2) / dot(e2, e2))));
  const s = Math.sign(e0[0] * e2[1] - e0[1] * e2[0]);
  const d0 = [dot(pq0, pq0), s * (v0[0] * e0[1] - v0[1] * e0[0])];
  const d1 = [dot(pq1, pq1), s * (v1[0] * e1[1] - v1[1] * e1[0])];
  const d2 = [dot(pq2, pq2), s * (v2[0] * e2[1] - v2[1] * e2[0])];
  const dDist = Math.min(d0[0], d1[0], d2[0]);
  const dSign = Math.min(d0[1], d1[1], d2[1]);
  return -Math.sqrt(dDist) * Math.sign(dSign);
}

function sdPolygon(px, py, v) {
  const n = v.length;
  let d = (px - v[0][0]) ** 2 + (py - v[0][1]) ** 2;
  let s = 1.0;
  for (let i = 0, j = n - 1; i < n; j = i, i++) {
    const e = [v[j][0] - v[i][0], v[j][1] - v[i][1]];
    const w = [px - v[i][0], py - v[i][1]];
    const t = clamp01(dot(w, e) / dot(e, e));
    const b = [w[0] - e[0] * t, w[1] - e[1] * t];
    d = Math.min(d, dot(b, b));
    const c1 = py >= v[i][1];
    const c2 = py < v[j][1];
    const c3 = e[0] * w[1] > e[1] * w[0];
    if ((c1 && c2 && c3) || (!c1 && !c2 && !c3)) s = -s;
  }
  return s * Math.sqrt(d);
}

const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const scale = (a, s) => [a[0] * s, a[1] * s];

function sdCircle(px, py, cx, cy, r) {
  return Math.hypot(px - cx, py - cy) - r;
}

// shield polygon centered at (cx,cy)
function shieldPoints(cx, cy, hw, hh) {
  const top = cy - hh;
  const bot = cy + hh;
  const shoulder = top + hh * 0.95;
  return [
    [cx - hw, top + hh * 0.12],
    [cx, top],
    [cx + hw, top + hh * 0.12],
    [cx + hw, shoulder - hh * 0.35],
    [cx + hw * 0.62, bot - hh * 0.18],
    [cx, bot],
    [cx - hw * 0.62, bot - hh * 0.18],
    [cx - hw, shoulder - hh * 0.35],
  ];
}

// ---------- renderer ----------
function renderIcon(size, { round = false } = {}) {
  const buf = Buffer.alloc(size * size * 4);
  const shield = shieldPoints(0.5, 0.455, 0.14, 0.165);
  // keyhole: a circle over a tapered stem (privacy / on-device lock)
  const keyholeCx = 0.5;
  const keyholeCy = 0.432;
  const keyholeR = 0.032;
  const keyStem = [
    [0.5 - 0.013, 0.45],
    [0.5 + 0.013, 0.45],
    [0.5 + 0.023, 0.522],
    [0.5 - 0.023, 0.522],
  ];
  // bubble body + tail
  const bubble = { cx: 0.5, cy: 0.44, hx: 0.275, hy: 0.225, r: 0.085 };
  const tail = [
    [0.355, 0.63],
    [0.47, 0.63],
    [0.30, 0.745],
  ];
  const px1 = 1 / size; // ~1px AA band in normalized units

  const cov = sd => clamp01(0.5 - sd / px1);

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const nx = (x + 0.5) / size;
      const ny = (y + 0.5) / size;

      // background diagonal gradient
      const tg = clamp01((nx + ny) / 2);
      let col = mixRgb(BG_TOP, BG_BOT, tg);

      // chat bubble (rounded body unioned with tail)
      const sdBody = sdRoundRect(
        nx,
        ny,
        bubble.cx,
        bubble.cy,
        bubble.hx,
        bubble.hy,
        bubble.r,
      );
      const sdTail = sdTriangle(nx, ny, tail[0], tail[1], tail[2]);
      const bubbleCov = cov(Math.min(sdBody, sdTail));
      col = mixRgb(col, WHITE, bubbleCov);

      // shield (gradient) inside bubble
      const shieldCov = cov(sdPolygon(nx, ny, shield));
      const ts = clamp01((ny - 0.3) / 0.34);
      col = mixRgb(col, mixRgb(SHIELD_TOP, SHIELD_BOT, ts), shieldCov);

      // keyhole (white) on the shield — privacy/lock
      const keyCov = cov(
        Math.min(
          sdCircle(nx, ny, keyholeCx, keyholeCy, keyholeR),
          sdPolygon(nx, ny, keyStem),
        ),
      );
      col = mixRgb(col, WHITE, keyCov);

      let a = 255;
      if (round) {
        const dx = nx - 0.5;
        const dy = ny - 0.5;
        const dist = Math.hypot(dx, dy);
        a = Math.round(255 * clamp01(0.5 - (dist - 0.5) / px1));
      }

      const i = (y * size + x) * 4;
      buf[i] = Math.round(clamp(col[0], 0, 255));
      buf[i + 1] = Math.round(clamp(col[1], 0, 255));
      buf[i + 2] = Math.round(clamp(col[2], 0, 255));
      buf[i + 3] = a;
    }
  }
  return buf;
}

// ---------- PNG encoder ----------
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
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}
function encodePng(rgba, size) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  // rest 0 (compression/filter/interlace)
  const stride = size * 4;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = zlib.deflateSync(raw, { level: 9 });
  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function writePng(file, size, opts) {
  const png = encodePng(renderIcon(size, opts), size);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, png);
  console.log('  wrote', path.relative(process.cwd(), file), `(${size}px)`);
}

// ---------- iOS ----------
const IOS_DIR = path.join(
  __dirname,
  '..',
  'ios',
  'EkamCore',
  'Images.xcassets',
  'AppIcon.appiconset',
);
const iosSizes = [40, 58, 60, 80, 87, 120, 180, 1024];
console.log('iOS:');
for (const s of iosSizes) writePng(path.join(IOS_DIR, `icon-${s}.png`), s);

const contents = {
  images: [
    { idiom: 'iphone', scale: '2x', size: '20x20', filename: 'icon-40.png' },
    { idiom: 'iphone', scale: '3x', size: '20x20', filename: 'icon-60.png' },
    { idiom: 'iphone', scale: '2x', size: '29x29', filename: 'icon-58.png' },
    { idiom: 'iphone', scale: '3x', size: '29x29', filename: 'icon-87.png' },
    { idiom: 'iphone', scale: '2x', size: '40x40', filename: 'icon-80.png' },
    { idiom: 'iphone', scale: '3x', size: '40x40', filename: 'icon-120.png' },
    { idiom: 'iphone', scale: '2x', size: '60x60', filename: 'icon-120.png' },
    { idiom: 'iphone', scale: '3x', size: '60x60', filename: 'icon-180.png' },
    {
      idiom: 'ios-marketing',
      scale: '1x',
      size: '1024x1024',
      filename: 'icon-1024.png',
    },
  ],
  info: { author: 'xcode', version: 1 },
};
fs.writeFileSync(
  path.join(IOS_DIR, 'Contents.json'),
  JSON.stringify(contents, null, 2),
);
console.log('  updated Contents.json');

// ---------- Android ----------
const ANDROID_RES = path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'res');
const androidSizes = {
  'mipmap-mdpi': 48,
  'mipmap-hdpi': 72,
  'mipmap-xhdpi': 96,
  'mipmap-xxhdpi': 144,
  'mipmap-xxxhdpi': 192,
};
if (fs.existsSync(ANDROID_RES)) {
  console.log('Android:');
  for (const [dir, s] of Object.entries(androidSizes)) {
    writePng(path.join(ANDROID_RES, dir, 'ic_launcher.png'), s);
    writePng(path.join(ANDROID_RES, dir, 'ic_launcher_round.png'), s, {
      round: true,
    });
  }
}

console.log('Done.');
