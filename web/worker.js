// Search worker: runs the chunked wasm search off the main thread, streams
// preview frames and progress, honors cancel between chunks. The final
// WasmSearch stays alive so the page can ask for a GIF afterwards.

import init, { load_image, WasmSearch } from './pkg/restring_wasm.js';

let search = null;
let cancelled = false;
let running = false;

const CHUNK = 250;
const PREVIEW_PX = 300;

self.onmessage = async (event) => {
  const msg = event.data;
  if (msg.type === 'start') {
    cancelled = false;
    running = true;
    try {
      await init();
      const photo = load_image(new Uint8Array(msg.bytes));
      const o = msg.options;
      search = new WasmSearch(photo, o.layout, o.step, o.pulls, o.strength,
                              o.weight > 0 ? o.weight : null,
                              o.palette || null, !!o.wb);
      const t0 = performance.now();
      while (!search.finished && !cancelled) {
        search.step(CHUNK);
        const png = search.render_png(PREVIEW_PX);
        self.postMessage({
          type: 'progress',
          pulls: search.pulls,
          budget: search.budget,
          png: png.buffer,
          quality: JSON.parse(search.quality_json()),
        }, [png.buffer]);
        // yield so cancel messages get processed between chunks
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      const seconds = ((performance.now() - t0) / 1000).toFixed(1);
      const png = search.render_png(600);
      self.postMessage({
        type: cancelled ? 'cancelled' : 'done',
        pulls: search.pulls,
        nails: search.nails_count,
        seconds,
        png: png.buffer,
        orders: JSON.parse(search.orders_json()),
        quality: JSON.parse(search.quality_json()),
      }, [png.buffer]);
    } catch (e) {
      self.postMessage({ type: 'error', message: String(e.message || e) });
    } finally {
      running = false;
    }
  } else if (msg.type === 'cancel') {
    cancelled = true;
  } else if (msg.type === 'gif') {
    if (!search) {
      self.postMessage({ type: 'error', message: 'no search to animate' });
      return;
    }
    try {
      const bytes = search.animation_gif(msg.size || 450, msg.frames || 180);
      self.postMessage({ type: 'gif', gif: bytes.buffer }, [bytes.buffer]);
    } catch (e) {
      self.postMessage({ type: 'error', message: String(e.message || e) });
    }
  }
};

self.postMessage({ type: 'ready' });