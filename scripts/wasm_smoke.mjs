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
import init, { load_image, generate, render_png } from '../web/pkg/restring_wasm.mjs';

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
