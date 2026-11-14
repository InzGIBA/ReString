// CI smoke test for the wasm binding: runs the real module in Node, no
// browser needed. Catches the binding-contract bugs a normal build cannot
// see (getter properties vs methods, wrong arg counts, render breakage).
//
// wasm-pack's web-target glue is an ES module emitted as .js, which Node
// loads as CommonJS without help; the pages workflow copies it to .mjs
// before calling this script. init() receives the wasm bytes directly,
// because Node's fetch does not read file:// URLs.

import { readFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import init, { load_image, generate, render_png, WasmSearch, render_project } from '../web/pkg/restring_wasm.mjs';

function crc32(buffer) {
  let table = crc32.table;
  if (!table) {
    table = crc32.table = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c;
    }
  }
  let crc = -1;
  for (const byte of buffer) crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ -1) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

// a valid 48x48 RGB PNG: a dark square with a bright corner, enough
// structure for the search to find improving pulls
function makeTestPng(size = 48) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // color type: RGB
  const rows = [];
  for (let y = 0; y < size; y++) {
    const row = Buffer.alloc(1 + size * 3);
    for (let x = 0; x < size; x++) {
      const v = x < size / 4 && y < size / 4 ? 230 : 40 + ((x + y) % 16) * 3;
      row[1 + x * 3] = v;
      row[2 + x * 3] = v;
      row[3 + x * 3] = v;
    }
    rows.push(row);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(Buffer.concat(rows))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const bytes = readFileSync(new URL('../web/pkg/restring_wasm_bg.wasm', import.meta.url));
await init(bytes);

const photo = load_image(new Uint8Array(makeTestPng()));
const art = generate(photo, 'rect', 4, 300, 0.1, null);

// the getter contract: these are properties on the exported class
if (typeof art.pulls !== 'number' || art.pulls <= 0) {
  throw new Error('art.pulls must be a positive number, got: ' + String(art.pulls));
}
if (typeof art.nails_count !== 'number' || art.nails_count <= 0) {
  throw new Error('art.nails_count must be a positive number, got: ' + String(art.nails_count));
}

const png = render_png(art, 300);
if (png.length < 1000) {
  throw new Error('render_png produced too few bytes: ' + png.length);
}

console.log(`wasm ok: ${art.pulls} pulls, ${art.nails_count} nails, ${png.length} png bytes`);

// --- chunked search: the worker path -------------------------------------
// same budget and strength as the one-shot run: chunking must not change
// the winding, the greedy state carries across steps
const chunked = new WasmSearch(photo, 'rect', 4, 300, 0.1, null, null, false);
let chunks = 0;
while (!chunked.finished) {
  chunked.step(100);
  chunks++;
}
if (chunked.pulls !== art.pulls) {
  throw new Error(`chunked search diverged: ${chunked.pulls} pulls vs ${art.pulls}`);
}
const chunkedOrders = JSON.parse(chunked.orders_json());
if (chunkedOrders.mode !== 'bw' || chunkedOrders.orders.length !== 1) {
  throw new Error('chunked orders_json must carry one bw order');
}
const quality = JSON.parse(chunked.quality_json());
if (!(quality.mse >= 0 && quality.ssim >= 0 && quality.ssim <= 1)) {
  throw new Error('quality_json out of range: ' + JSON.stringify(quality));
}
console.log(`chunked ok: ${chunks} chunks, mse ${quality.mse}, ssim ${quality.ssim}`);

// --- color search: cmyk palette, project round trip, GIF ------------------
const color = new WasmSearch(photo, 'rect', 4, 200, 0, null, 'cmyk', false);
while (!color.finished) color.step(100);
const orders = JSON.parse(color.orders_json());
if (orders.mode !== 'palette' || orders.orders.length !== 4 || orders.palette.length !== 4) {
  throw new Error('cmyk search must carry four orders and four palette colors');
}
const colorPng = color.render_png(300);
if (colorPng.length < 1000) {
  throw new Error('color render_png produced too few bytes: ' + colorPng.length);
}

const project = {
  format: 'restring-project', version: 2, mode: orders.mode,
  config: { grid: 300, wb: false },
  nails: orders.nails, pull_orders: orders.orders, palette: orders.palette,
  input_digest: '', created: '', restring_version: 'smoke',
};
const projectPng = render_project(JSON.stringify(project), 300, 0);
if (projectPng.length < 1000) {
  throw new Error('render_project produced too few bytes: ' + projectPng.length);
}

const gif = color.animation_gif(120, 12);
if (gif.length < 1000 || Buffer.from(gif.slice(0, 4)).toString('ascii') !== 'GIF8') {
  throw new Error('animation_gif must produce GIF bytes, got ' + gif.length);
}
console.log(`color ok: ${color.pulls} pulls, ${colorPng.length} png bytes, ${gif.length} gif bytes`);

// --- white on black --------------------------------------------------------
const wb = new WasmSearch(photo, 'circle', 4, 100, 0, null, null, true);
while (!wb.finished) wb.step(50);
const wbOrders = JSON.parse(wb.orders_json());
if (wbOrders.wb !== true || wbOrders.mode !== 'bw') {
  throw new Error('wb search must report wb true and mode bw');
}
console.log(`wb ok: ${wb.pulls} pulls`);
