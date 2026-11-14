// Winding poster as printable SVG, the browser twin of restring.poster:
// A3 landscape, millimeter viewBox, numbered nails, thread-length footer.
// Consumes the project-shaped payload from WasmSearch.orders_json() or a
// loaded .restring file.

const LEAD_IN_MM = 150.0;
const SLACK = 1.05;
const PAGE_W = 420.0;
const PAGE_H = 297.0;
const MARGIN = 10.0;
const FOOTER = 16.0;
const CHANNEL_COLORS = ['#c22222', '#22a04a', '#2244cc'];
const NAIL_COLOR = '#222222';

function gridSides(project) {
  const grid = (project.config && project.config.grid) || 300;
  return Array.isArray(grid) ? [grid[0], grid[1]] : [grid, grid];
}

export function threadLengthsMm(project, canvasMm) {
  const [gh, gw] = gridSides(project);
  const sy = canvasMm / gh;
  const sx = canvasMm / gw;
  return project.pull_orders.map((order) => {
    let dist = 0;
    for (let i = 0; i + 1 < order.length; i++) {
      const [r1, c1] = project.nails[order[i]];
      const [r2, c2] = project.nails[order[i + 1]];
      dist += Math.hypot((r2 - r1) * sy, (c2 - c1) * sx);
    }
    return dist * SLACK + 2 * LEAD_IN_MM;
  });
}

function hex(rgb) {
  return '#' + rgb.map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
}

function threadColors(project) {
  if (project.mode === 'bw') return [NAIL_COLOR];
  if (project.mode === 'rgb') return CHANNEL_COLORS;
  return project.palette.map((t) => (Math.min(...t.rgb) > 0.85 ? NAIL_COLOR : hex(t.rgb)));
}

function threadNames(project) {
  if (project.mode === 'bw') return [project.config && project.config.wb ? 'white' : 'black'];
  if (project.mode === 'rgb') return ['red', 'green', 'blue'];
  return project.palette.map((t) => t.name);
}

function escapeXml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function posterSvg(project, { canvasMm = 260, numberEvery = 10, preview = false } = {}) {
  const maxBoard = Math.min(PAGE_W, PAGE_H) - 2 * MARGIN - FOOTER;
  if (!(canvasMm > 0 && canvasMm <= maxBoard)) {
    throw new Error(`board of ${canvasMm} mm does not fit the page, max ${maxBoard} mm`);
  }
  const [gh, gw] = gridSides(project);
  const boardX = (PAGE_W - canvasMm) / 2;
  const boardY = MARGIN;
  const sx = canvasMm / gw;
  const sy = canvasMm / gh;
  const centerR = gh / 2;
  const centerC = gw / 2;
  const xy = (nail) => [boardX + nail[1] * sx, boardY + nail[0] * sy];

  const out = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    `<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="${PAGE_W}mm" height="${PAGE_H}mm" viewBox="0 0 ${PAGE_W} ${PAGE_H}">`,
    `<rect x="0" y="0" width="${PAGE_W}" height="${PAGE_H}" fill="white"/>`,
    `<rect x="${boardX}" y="${boardY}" width="${canvasMm}" height="${canvasMm}" fill="none" stroke="${NAIL_COLOR}" stroke-width="0.3"/>`,
  ];

  if (preview) {
    const colors = threadColors(project);
    project.pull_orders.forEach((order, k) => {
      const segments = [];
      for (let i = 0; i + 1 < order.length; i++) {
        const [x1, y1] = xy(project.nails[order[i]]);
        const [x2, y2] = xy(project.nails[order[i + 1]]);
        segments.push(`<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}"/>`);
      }
      out.push(`<g stroke="${colors[k]}" stroke-width="0.25" opacity="0.1">${segments.join('')}</g>`);
    });
  }

  project.nails.forEach((nail, i) => {
    const [x, y] = xy(nail);
    if (i === 0) {
      out.push(`<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="1.5" fill="white" stroke="#c22222" stroke-width="0.5"/>`);
    } else {
      out.push(`<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="1" fill="${NAIL_COLOR}"/>`);
    }
  });

  if (numberEvery > 0) {
    const labels = [];
    project.nails.forEach((nail, i) => {
      if (i % numberEvery) return;
      const [x, y] = xy(nail);
      const dx = nail[1] - centerC;
      const dy = nail[0] - centerR;
      const norm = Math.hypot(dx, dy) || 1;
      const lx = x + (dx / norm) * 4.5;
      const ly = y + (dy / norm) * 4.5 + 0.9;
      labels.push(`<text x="${lx.toFixed(2)}" y="${ly.toFixed(2)}" font-size="2.6" font-family="Helvetica, Arial, sans-serif" fill="${NAIL_COLOR}" text-anchor="middle">${i}</text>`);
    });
    out.push(labels.join(''));
  }

  const pulls = project.pull_orders.map((o) => o.length - 1);
  const lengthsM = threadLengthsMm(project, canvasMm).map((mm) => mm / 1000);
  const names = threadNames(project);
  const threadInfo = project.mode === 'bw'
    ? `Threads: 1, thread length: ${lengthsM[0].toFixed(0)} m`
    : `Threads: ${names.length} (${names.map(escapeXml).join('/')}), thread lengths: ${lengthsM.map((v) => v.toFixed(0)).join('/')} m`;
  const date = project.created || '-';
  out.push(`<text x="${MARGIN}" y="${PAGE_H - FOOTER + 4}" font-size="3.4" font-family="Helvetica, Arial, sans-serif" fill="${NAIL_COLOR}">Nails: ${project.nails.length}, Pulls: ${pulls.join('/')}, ${threadInfo}</text>`);
  out.push(`<text x="${MARGIN}" y="${PAGE_H - FOOTER + 9}" font-size="3" font-family="Helvetica, Arial, sans-serif" fill="${NAIL_COLOR}">ReString web, ${escapeXml(date)}, board ${canvasMm} mm, print at 100% scale</text>`);
  out.push('</svg>');
  return out.join('\n');
}

export function windingCsv(project) {
  const rows = ['thread,pull,from_nail,to_nail'];
  project.pull_orders.forEach((order, k) => {
    for (let i = 0; i + 1 < order.length; i++) {
      rows.push(`${k + 1},${i},${order[i]},${order[i + 1]}`);
    }
  });
  return rows.join('\n') + '\n';
}

export function windingTxt(project) {
  const names = threadNames(project);
  const lengths = threadLengthsMm(project, 400);
  const out = [`# nails: ${project.nails.length}`, `# threads: ${names.length}`];
  names.forEach((name, k) => {
    out.push(`# thread ${k + 1}: ${name}, ${project.pull_orders[k].length - 1} pulls, ${(lengths[k] / 1000).toFixed(0)} m at 400 mm board`);
  });
  project.pull_orders.forEach((order) => out.push(order.join(' ')));
  return out.join('\n') + '\n';
}