//! ReString core: rasterizer, line cache, greedy search, renderers,
//! animation frames and metrics. Platform-neutral plain Rust, no pyo3 and
//! no Python types. The CPython binding (rust/) and the wasm binding
//! (rust/wasm/) wrap this crate.

use std::collections::HashSet;

// ---------------------------------------------------------------------------
// Image container
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct Image {
    pub data: Vec<f64>, // row-major, ch interleaved
    pub w: usize,
    pub h: usize,
    pub ch: usize,
}


impl Image {
    pub fn at(&self, r: usize, c: usize, k: usize) -> f64 {
        self.data[(r * self.w + c) * self.ch + k]
    }
    pub fn set(&mut self, r: usize, c: usize, k: usize, v: f64) {
        let idx = (r * self.w + c) * self.ch + k;
        self.data[idx] = v;
    }
}


impl Image {
    /// Separable box blur with a (2*radius+1) window: two passes over
    /// running sums, O(w*h) regardless of radius, edges replicate. Works on
    /// grayscale and per-channel color.
    pub fn box_blur(&self, radius: usize) -> Image {
        let (w, h, ch) = (self.w, self.h, self.ch);
        let r = radius.min(w.max(h));
        let mut tmp = vec![0.0f64; self.data.len()];
        let mut out = vec![0.0f64; self.data.len()];
        // horizontal pass: sliding [c - r, c + r] window with clamped edges
        for row in 0..h {
            for k in 0..ch {
                let at = |c: usize| self.data[(row * w + c) * ch + k];
                let mut lo: i64 = 0;
                let mut hi: i64 = -1;
                let mut running = 0.0f64;
                for c in 0..w {
                    let want_hi = (c + r).min(w - 1) as i64;
                    while hi < want_hi {
                        hi += 1;
                        running += at(hi as usize);
                    }
                    let want_lo = (c as i64 - r as i64).max(0);
                    while lo < want_lo {
                        running -= at(lo as usize);
                        lo += 1;
                    }
                    tmp[(row * w + c) * ch + k] = running / (hi - lo + 1) as f64;
                }
            }
        }
        // vertical pass over the horizontal result
        for c in 0..w {
            for k in 0..ch {
                let at = |rr: usize| tmp[(rr * w + c) * ch + k];
                let mut lo: i64 = 0;
                let mut hi: i64 = -1;
                let mut running = 0.0f64;
                for row in 0..h {
                    let want_hi = (row + r).min(h - 1) as i64;
                    while hi < want_hi {
                        hi += 1;
                        running += at(hi as usize);
                    }
                    let want_lo = (row as i64 - r as i64).max(0);
                    while lo < want_lo {
                        running -= at(lo as usize);
                        lo += 1;
                    }
                    out[(row * w + c) * ch + k] = running / (hi - lo + 1) as f64;
                }
            }
        }
        Image { data: out, w, h, ch }
    }

    /// Load a PNG/JPEG file as an RGB float image in [0, 1].
    pub fn load(path: &str) -> Result<Image, String> {
        let opened = image::ImageReader::open(path)
            .map_err(|e| format!("cannot open {path}: {e}"))?
            .decode()
            .map_err(|e| format!("cannot decode {path}: {e}"))?;
        let rgb = opened.to_rgb8();
        let (w, h) = rgb.dimensions();
        let data = rgb.into_raw().iter().map(|&b| b as f64 / 255.0).collect();
        Ok(Image { data, w: w as usize, h: h as usize, ch: 3 })
    }

    /// Uniform canvas of the given value (1.0 = white, 0.0 = black).
    pub fn blank(w: usize, h: usize, ch: usize, value: f64) -> Image {
        Image { data: vec![value; w * h * ch], w, h, ch }
    }

    /// Build from nested gray lists: h x w. The Python wrapper handles the
    /// h x w x 3 RGB case and the ragged-list validation on the boundary.
    pub fn from_gray(rows: &[Vec<f64>]) -> Result<Image, String> {
        let h = rows.len();
        let w = rows.first().map(|r| r.len()).unwrap_or(0);
        let mut data = Vec::with_capacity(h * w);
        for row in rows {
            if row.len() != w {
                return Err("ragged nested image".to_string());
            }
            data.extend_from_slice(row);
        }
        Ok(Image { data, w, h, ch: 1 })
    }

    /// Build from nested RGB lists: h x w x 3.
    pub fn from_rgb(rows: &[Vec<Vec<f64>>]) -> Result<Image, String> {
        let h = rows.len();
        let w = rows.first().map(|r| r.len()).unwrap_or(0);
        let mut data = Vec::with_capacity(h * w * 3);
        for row in rows {
            for px in row {
                if px.len() != 3 {
                    return Err("ragged nested image".to_string());
                }
                data.extend_from_slice(px);
            }
        }
        Ok(Image { data, w, h, ch: 3 })
    }

    pub fn shape(&self) -> (usize, usize, usize) {
        (self.h, self.w, self.ch)
    }

    pub fn pixel_checked(&self, r: usize, c: usize, k: usize) -> Result<f64, String> {
        if r >= self.h || c >= self.w || k >= self.ch {
            return Err("pixel index out of range".to_string());
        }
        Ok(self.at(r, c, k))
    }

    /// Nested gray lists (ch == 1). The RGB case lives in to_list_rgb so the
    /// Python boundary picks the return shape.
    pub fn to_list(&self) -> Vec<Vec<f64>> {
        let mut rows = Vec::with_capacity(self.h);
        for r in 0..self.h {
            rows.push((0..self.w).map(|c| self.at(r, c, 0)).collect());
        }
        rows
    }

    /// Nested RGB lists (ch == 3).
    pub fn to_list_rgb(&self) -> Vec<Vec<Vec<f64>>> {
        let mut rows = Vec::with_capacity(self.h);
        for r in 0..self.h {
            let mut row = Vec::with_capacity(self.w);
            for c in 0..self.w {
                row.push((0..self.ch).map(|k| self.at(r, c, k)).collect::<Vec<f64>>());
            }
            rows.push(row);
        }
        rows
    }

    /// Central largest square crop (port of image_transformations.largest_square).
    pub fn largest_square(&self) -> Self {
        let short = if self.h <= self.w { 0 } else { 1 };
        let short_half = if short == 0 { self.h / 2 } else { self.w / 2 };
        let long_center = if short == 0 { self.w / 2 } else { self.h / 2 };
        let (y0, y1, x0, x1) = if short == 0 {
            (0, self.h, long_center - short_half, long_center + short_half)
        } else {
            (long_center - short_half, long_center + short_half, 0, self.w)
        };
        let w = x1 - x0;
        let h = y1 - y0;
        let mut data = Vec::with_capacity(w * h * self.ch);
        for r in y0..y1 {
            let start = (r * self.w + x0) * self.ch;
            data.extend_from_slice(&self.data[start..start + w * self.ch]);
        }
        Image { data, w, h, ch: self.ch }
    }

    /// Anti-aliased box/bilinear resample (port of image_transformations.resize).
    pub fn resize(&self, out_w: usize, out_h: usize) -> Self {
        let row_terms = resample_terms(self.h, out_h);
        let col_terms = resample_terms(self.w, out_w);
        let mut tmp = vec![0.0; out_h * self.w * self.ch];
        for (oy, terms) in row_terms.iter().enumerate() {
            for ix in 0..self.w {
                for k in 0..self.ch {
                    let mut acc = 0.0;
                    for &(idx, wgt) in terms {
                        acc += wgt * self.at(idx, ix, k);
                    }
                    tmp[(oy * self.w + ix) * self.ch + k] = acc;
                }
            }
        }
        let mut out = vec![0.0; out_h * out_w * self.ch];
        for oy in 0..out_h {
            for (ox, terms) in col_terms.iter().enumerate() {
                for k in 0..self.ch {
                    let mut acc = 0.0;
                    for &(idx, wgt) in terms {
                        acc += wgt * tmp[(oy * self.w + idx) * self.ch + k];
                    }
                    out[(oy * out_w + ox) * self.ch + k] = acc;
                }
            }
        }
        Image { data: out, w: out_w, h: out_h, ch: self.ch }
    }

    /// Grayscale (port of image_transformations.rgb2gray, times `scale`).
    pub fn gray(&self, scale: f64) -> Result<Image, String> {
        if self.ch != 3 {
            return Err("gray() needs an RGB image".to_string());
        }
        let mut data = Vec::with_capacity(self.w * self.h);
        for px in self.data.chunks_exact(3) {
            data.push((0.2989 * px[0] + 0.5870 * px[1] + 0.1140 * px[2]) * scale);
        }
        Ok(Image { data, w: self.w, h: self.h, ch: 1 })
    }

    /// Single channel of an RGB image as a gray image.
    pub fn channel(&self, k: usize) -> Result<Image, String> {
        if k >= self.ch {
            return Err("channel index out of range".to_string());
        }
        let mut data = Vec::with_capacity(self.w * self.h);
        for r in 0..self.h {
            for c in 0..self.w {
                data.push(self.at(r, c, k));
            }
        }
        Ok(Image { data, w: self.w, h: self.h, ch: 1 })
    }

    /// Save as 8-bit PNG (L for gray, RGB otherwise); values clipped to [0, 1].
    pub fn save_png(&self, path: &str) -> Result<(), String> {
        let to_u8 = |v: f64| (v.clamp(0.0, 1.0) * 255.0) as u8;
        let result = if self.ch == 1 {
            image::ImageBuffer::<image::Luma<u8>, Vec<u8>>::from_fn(
                self.w as u32, self.h as u32,
                |x, y| image::Luma([to_u8(self.at(y as usize, x as usize, 0))]),
            )
            .save(&path)
        } else {
            image::ImageBuffer::<image::Rgb<u8>, Vec<u8>>::from_fn(
                self.w as u32, self.h as u32,
                |x, y| image::Rgb([
                    to_u8(self.at(y as usize, x as usize, 0)),
                    to_u8(self.at(y as usize, x as usize, 1)),
                    to_u8(self.at(y as usize, x as usize, 2)),
                ]),
            )
            .save(&path)
        };
        result.map_err(|e| format!("cannot save {path}: {e}"))
    }
}

/// Sparse resample weights: for each output row/col, (input index, weight)
/// pairs summing to 1. Downscale = exact area overlap (anti-aliased box),
/// upscale = bilinear on pixel centers — port of _bin_weights.
fn resample_terms(n_in: usize, n_out: usize) -> Vec<Vec<(usize, f64)>> {
    if n_out >= n_in {
        let scale = n_in as f64 / n_out as f64;
        (0..n_out)
            .map(|k| {
                let src = (k as f64 + 0.5) * scale - 0.5;
                let i0 = src.floor();
                let frac = src - i0;
                let lo = (i0 as i64).clamp(0, n_in as i64 - 1) as usize;
                let hi = (i0 as i64 + 1).clamp(0, n_in as i64 - 1) as usize;
                if lo == hi {
                    vec![(lo, 1.0)]
                } else {
                    vec![(lo, 1.0 - frac), (hi, frac)]
                }
            })
            .collect()
    } else {
        let scale = n_in as f64 / n_out as f64;
        (0..n_out)
            .map(|k| {
                let e0 = k as f64 * scale;
                let e1 = e0 + scale;
                let mut terms: Vec<(usize, f64)> = Vec::new();
                let mut acc = 0.0;
                let i_start = e0.floor() as usize;
                let i_end = (e1.ceil() as usize).min(n_in);
                for i in i_start..i_end {
                    let cover = (i as f64 + 1.0).min(e1) - (i as f64).max(e0);
                    if cover > 0.0 {
                        terms.push((i, cover));
                        acc += cover;
                    }
                }
                for t in terms.iter_mut() {
                    t.1 /= acc;
                }
                terms
            })
            .collect()
    }
}


// ---------------------------------------------------------------------------
// Zingl anti-aliased line rasterizer (identical to restring.canvas.line_aa)
// ---------------------------------------------------------------------------

pub fn zingl_line(r0: i64, c0: i64, r1: i64, c1: i64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    let mut rr: Vec<i64> = Vec::new();
    let mut cc: Vec<i64> = Vec::new();
    let mut val: Vec<f64> = Vec::new();

    let dc = (c0 - c1).abs();
    let dr = (r0 - r1).abs();
    let mut err = (dc - dr) as f64;

    let sign_c: i64 = if c0 < c1 { 1 } else { -1 };
    let sign_r: i64 = if r0 < r1 { 1 } else { -1 };
    let ed: f64 = if dc + dr == 0 {
        1.0
    } else {
        ((dc * dc + dr * dr) as f64).sqrt()
    };

    let mut c = c0;
    let mut r = r0;
    loop {
        cc.push(c);
        rr.push(r);
        val.push(((err - dc as f64 + dr as f64).abs()) / ed);

        let err_prime = err;
        let c_prime = c;

        if 2.0 * err_prime >= -(dc as f64) {
            if c == c1 {
                break;
            }
            if (err_prime + dr as f64) < ed {
                cc.push(c);
                rr.push(r + sign_r);
                val.push((err_prime + dr as f64).abs() / ed);
            }
            err -= dr as f64;
            c += sign_c;
        }

        if 2.0 * err_prime <= dr as f64 {
            if r == r1 {
                break;
            }
            if (dc as f64 - err_prime) < ed {
                cc.push(c_prime + sign_c);
                rr.push(r);
                val.push((dc as f64 - err_prime).abs() / ed);
            }
            err += dc as f64;
            r += sign_r;
        }
    }

    for v in val.iter_mut() {
        *v = 1.0 - *v;
    }
    (rr, cc, val)
}

/// Anti-aliased line — exposed for tests and the Python reference port.
pub fn line_aa(r0: i64, c0: i64, r1: i64, c1: i64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    zingl_line(r0, c0, r1, c1)
}

// ---------------------------------------------------------------------------
// Nail layouts (ports of restring.nails)
// ---------------------------------------------------------------------------

/// Midpoint ellipse boundary — pixel-set identical to the Python port.
pub fn ellipse_perimeter(cr: i64, cc_: i64, r_radius: i64, c_radius: i64) -> Vec<(i64, i64)> {
    let (a, b) = (c_radius, r_radius);
    let (a2, b2) = ((a * a) as f64, (b * b) as f64);
    let mut points: HashSet<(i64, i64)> = HashSet::new();
    let mut plot4 = |x: i64, y: i64, points: &mut HashSet<(i64, i64)>| {
        for (dy, dx) in [(y, x), (y, -x), (-y, x), (-y, -x)] {
            points.insert((cr + dy, cc_ + dx));
        }
    };

    let (mut x, mut y) = (0i64, b);
    let (mut dx, mut dy) = (2.0 * b2 * x as f64, 2.0 * a2 * y as f64);
    let mut d1 = b2 - a2 * b as f64 + a2 / 4.0;
    while dx < dy {
        plot4(x, y, &mut points);
        if d1 < 0.0 {
            x += 1;
            dx += 2.0 * b2;
            d1 += dx + b2;
        } else {
            x += 1;
            y -= 1;
            dx += 2.0 * b2;
            dy -= 2.0 * a2;
            d1 += dx - dy + b2;
        }
    }
    let mut d2 = b2 * (x as f64 + 0.5).powi(2) + a2 * (y as f64 - 1.0).powi(2) - a2 * b2;
    while y >= 0 {
        plot4(x, y, &mut points);
        if d2 > 0.0 {
            y -= 1;
            dy -= 2.0 * a2;
            d2 += a2 - dy;
        } else {
            y -= 1;
            x += 1;
            dx += 2.0 * b2;
            dy -= 2.0 * a2;
            d2 += dx - dy + a2;
        }
    }
    points.into_iter().collect()
}

/// Circle/ellipse nails, sorted clockwise from 9 o'clock (port of
/// restring.nails.create_circle_nail_positions).
pub fn circle_nails(w: usize, h: usize, nail_step: usize, r1_mult: f64, r2_mult: f64) -> Vec<(i64, i64)> {
    let centre = (h as i64 / 2, w as i64 / 2);
    let radius = (h.min(w) as i64 / 2 - 1).max(0);
    let mut nails = ellipse_perimeter(
        centre.0,
        centre.1,
        (radius as f64 * r1_mult) as i64,
        (radius as f64 * r2_mult) as i64,
    );
    nails.sort_by(|a, b| {
        let aa = (a.0 as f64 - centre.0 as f64).atan2(a.1 as f64 - centre.1 as f64);
        let bb = (b.0 as f64 - centre.0 as f64).atan2(b.1 as f64 - centre.1 as f64);
        aa.partial_cmp(&bb).unwrap()
    });
    nails.into_iter().step_by(nail_step.max(1)).collect()
}

/// Rectangle border nails, clockwise from the top-left corner.
pub fn rect_nails(w: usize, h: usize, nail_step: usize) -> Vec<(i64, i64)> {
    let step = nail_step.max(1) as i64;
    let (w, h) = (w as i64, h as i64);
    let mut nails = Vec::new();
    for c in (0..w).step_by(step as usize) {
        nails.push((0, c)); // top
    }
    for r in (1..h - 1).step_by(step as usize) {
        nails.push((r, w - 1)); // right
    }
    for c in (0..w).step_by(step as usize) {
        nails.push((h - 1, c)); // bottom
    }
    for r in (1..h - 1).step_by(step as usize) {
        nails.push((r, 0)); // left
    }
    nails
}

// ---------------------------------------------------------------------------
// Greedy search (port of restring.generator.create_art)
// ---------------------------------------------------------------------------

pub struct SourceLines {
    flat_idx: Vec<u32>,
    val: Vec<f64>,
    bounds: Vec<usize>,
    targets: Vec<u32>,
}

/// Deterministic splitmix64 — self-contained seeded RNG (no external crates).
pub struct SplitMix64(u64);

impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }
}

/// Deterministic random subset of `k` indices from `0..n` (Floyd's algorithm,
/// returned in ascending order so tie-breaking matches the full scan).
pub fn seeded_subset(n: usize, k: usize, seed: u64) -> Vec<usize> {
    let mut rng = SplitMix64(seed);
    let mut set = HashSet::new();
    for j in (n - k)..n {
        let t = (rng.next() % (j as u64 + 1)) as usize;
        if set.contains(&t) {
            set.insert(j);
        } else {
            set.insert(t);
        }
    }
    let mut v: Vec<usize> = set.into_iter().collect();
    v.sort_unstable();
    v
}

/// Build the line cache for a chunk of source nails (parallelizable unit).
pub fn build_sources(nails: &[(i64, i64)], range: std::ops::Range<usize>, w: usize) -> Vec<SourceLines> {
    let n = nails.len();
    let flat = |r: i64, c: i64| (r as usize * w + c as usize) as u32;
    let mut sources = Vec::with_capacity(range.len());
    for i in range {
        let mut sl = SourceLines {
            flat_idx: Vec::new(),
            val: Vec::new(),
            bounds: vec![0],
            targets: Vec::new(),
        };
        for j in 0..n {
            if j == i {
                continue;
            }
            let (rr, cc, val) = zingl_line(nails[i].0, nails[i].1, nails[j].0, nails[j].1);
            for k in 0..rr.len() {
                sl.flat_idx.push(flat(rr[k], cc[k]));
                sl.val.push(val[k]);
            }
            sl.bounds.push(sl.val.len());
            sl.targets.push(j as u32);
        }
        sources.push(sl);
    }
    sources
}

/// Summed squared-error improvement of applying one cached line segment. An
/// empty `weight_map` scores plain MSE; otherwise each pixel's contribution
/// is scaled by the map value (importance weighting).
#[inline]
pub fn seg_improvement(
    sl: &SourceLines,
    pic: &[f64],
    orig: &[f64],
    weight_map: &[f64],
    s0: usize,
    s1: usize,
    strength: f64,
) -> f64 {
    let mut improvement = 0.0f64;
    if weight_map.is_empty() {
        for k in s0..s1 {
            let px = sl.flat_idx[k] as usize;
            let cur = pic[px];
            let new = (cur + strength * sl.val[k]).clamp(0.0, 1.0);
            let o = orig[px];
            improvement += (cur - o) * (cur - o) - (new - o) * (new - o);
        }
    } else {
        for k in s0..s1 {
            let px = sl.flat_idx[k] as usize;
            let cur = pic[px];
            let new = (cur + strength * sl.val[k]).clamp(0.0, 1.0);
            let o = orig[px];
            improvement += weight_map[px] * ((cur - o) * (cur - o) - (new - o) * (new - o));
        }
    }
    improvement
}

/// Forward a debug note to the Python logging module (logger restring.core).
/// Greedy pull-order search on the given grayscale target. Returns the pull
/// order and the final working canvas. With `random_nails = Some(k)` only a
/// fixed seeded subset of k candidates is scanned each iteration. With
/// `weights = Some(map)` each pixel's error contribution is multiplied by the
/// map value (the scan_candidates_weighted scoring), so threads concentrate
/// on high-weight regions. Without weights the arithmetic is unchanged. With
/// `min_chord = Some(d)` candidates closer than d pixels are skipped; on a
/// dead end (every chord from the current nail is masked out) the search
/// takes the best masked-out pull once instead of stalling. With
/// `rollback = true` the returned order truncates to the prefix where the
/// running canvas error hit its minimum — zero and negative improvement
/// tails vanish. Default false: the full order, bit-identical to v1.1.
///
/// The line cache is rasterized in parallel (result-preserving: each line is
/// deterministic, chunks are reassembled in source order).
///
/// An incremental improvement cache was evaluated here and rejected — see
/// docs/optimization.md (stage 7): with canvas-crossing chords the per-line
/// invalidation fan-out rivals the full rescan cost, so the cache measured
/// 0.4-0.6x of the plain scan throughput.
pub fn create_art(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    strength: f64,
    i_limit: Option<u64>,
    random_nails: Option<u64>,
    white: bool,
    weights: Option<&Image>,
    min_chord: Option<f64>,
    rollback: bool,
    seed: Option<u64>,
    mut messages: Option<&mut Vec<(String, String)>>,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 {
        return Err("create_art needs a grayscale target".to_string());
    }
    let weight_map: Vec<f64> = match weights {
        None => Vec::new(),
        Some(w) => {
            if w.ch != 1 || w.w != orig.w || w.h != orig.h {
                return Err("weights must be grayscale with the same shape as orig".to_string());
            }
            w.data.clone()
        }
    };
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();

    let order: Vec<usize> = match random_nails {
        None => (0..n).collect(),
        Some(k) => seeded_subset(n, k as usize, seed.unwrap_or(42)),
    };

    // parallel rasterization across sources
    let sources = build_line_cache(&nails, w, n);

    // per-source candidate masks: allowed[seg] keeps chords at or above the
    // minimum distance. Distance in pixels, not nail indices, so the filter
    // behaves the same on circle, rectangle and custom layouts.
    let min_chord_sq = min_chord.map(|d| d * d);
    let masks: Vec<Vec<bool>> = match min_chord_sq {
        None => Vec::new(),
        Some(mc2) => sources
            .iter()
            .enumerate()
            .map(|(i, sl)| {
                sl.targets
                    .iter()
                    .map(|&t| {
                        let (dr, dc) = (
                            (nails[t as usize].0 - nails[i].0) as f64,
                            (nails[t as usize].1 - nails[i].1) as f64,
                        );
                        dr * dr + dc * dc >= mc2
                    })
                    .collect()
            })
            .collect(),
    };

    let mut pic = vec![if white { 1.0 } else { 0.0 }; w * h];
    let mut pull_order: Vec<u64> = vec![0];
    let mut current = 0usize;
    let mut i = 0u64;
    let mut fails = 0u32;
    let mut recovery_logged = false;

    // best-prefix tracking: the blank canvas error minus the improvements of
    // every applied pull telescopes into the true canvas error, so the
    // minimum marks the best prefix exactly
    let initial_fill = if white { 1.0 } else { 0.0 };
    let mut running_error: f64 = orig
        .data
        .iter()
        .map(|o| (initial_fill - o) * (initial_fill - o))
        .sum();
    let mut best_error = running_error;
    let mut best_len = 0usize;

    loop {
        i += 1;

        match i_limit {
            None => {
                if fails >= 3 {
                    break;
                }
            }
            Some(limit) => {
                if i > limit {
                    break;
                }
            }
        }

        let sl = &sources[current];
        let allowed: &[bool] = if masks.is_empty() { &[] } else { &masks[current] };
        let mut best_target: u64 = 0;
        let mut best_improvement = f64::NEG_INFINITY;
        let mut best_range = (0usize, 0usize);
        let mut fb_target: u64 = 0;
        let mut fb_improvement = f64::NEG_INFINITY;
        let mut fb_range = (0usize, 0usize);
        let mut allowed_seen = false;

        for &cand in &order {
            if cand == current || cand >= n {
                continue;
            }
            let seg = match sl.targets.binary_search(&(cand as u32)) {
                Ok(pos) => pos,
                Err(_) => continue,
            };
            let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
            let improvement = seg_improvement(sl, &pic, &orig.data, &weight_map, s0, s1, strength);
            if !allowed.is_empty() && !allowed[seg] {
                // masked out: rank it anyway, recovery may need it
                if improvement > fb_improvement {
                    fb_improvement = improvement;
                    fb_target = cand as u64;
                    fb_range = (s0, s1);
                }
                continue;
            }
            allowed_seen = true;
            if improvement >= best_improvement {
                best_improvement = improvement;
                best_target = cand as u64;
                best_range = (s0, s1);
            }
        }

        if best_improvement <= 0.0 {
            if allowed_seen || fb_improvement <= 0.0 {
                fails += 1;
                continue;
            }
            // dead-end recovery: every chord from this nail sits under the
            // threshold, take the best masked-out pull once instead of stalling
            if !recovery_logged {
                recovery_logged = true;
                if let Some(sink) = messages.as_deref_mut() {
                    sink.push(("debug".to_string(), "min-chord dead end: no candidate clears the threshold, taking the best masked-out pull".to_string()));
                }
            }
            best_target = fb_target;
            best_range = fb_range;
            best_improvement = fb_improvement;
        }

        pull_order.push(best_target);
        running_error -= best_improvement;
        for k in best_range.0..best_range.1 {
            let px = sl.flat_idx[k] as usize;
            pic[px] = (pic[px] + strength * sl.val[k]).clamp(0.0, 1.0);
        }
        current = best_target as usize;
        if running_error < best_error {
            best_error = running_error;
            best_len = pull_order.len() - 1;
        }
    }

    if rollback && pull_order.len() - 1 > best_len {
        if let Some(sink) = messages.as_deref_mut() {
            sink.push(("info".to_string(), format!("Rolled back {} of {} pulls", pull_order.len() - 1 - best_len, pull_order.len() - 1)));
        }
        pull_order.truncate(best_len + 1);
    }

    Ok((pull_order, Image { data: pic, w, h, ch: 1 }))
}

// ---------------------------------------------------------------------------
// Experimental lookahead searches: beam width, receding horizon (MPC)
// ---------------------------------------------------------------------------

/// One beam hypothesis: a partial pull sequence with its own working canvas.
pub struct BeamState {
    pic: Vec<f64>,
    current: usize,
    score: f64,
    order: Vec<u64>,
}

/// Scan every candidate pull from `state`. Read-only against the canvas.
pub fn scan_candidates(
    sources: &[SourceLines],
    order: &[usize],
    n: usize,
    orig: &[f64],
    strength: f64,
    state: &BeamState,
) -> Vec<(f64, u32, usize, usize)> {
    let sl = &sources[state.current];
    let mut out = Vec::with_capacity(order.len());
    for &cand in order {
        if cand == state.current || cand >= n {
            continue;
        }
        let seg = match sl.targets.binary_search(&(cand as u32)) {
            Ok(pos) => pos,
            Err(_) => continue,
        };
        let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
        let mut improvement = 0.0f64;
        for k in s0..s1 {
            let px = sl.flat_idx[k] as usize;
            let cur = state.pic[px];
            let new = (cur + strength * sl.val[k]).clamp(0.0, 1.0);
            let o = orig[px];
            improvement += (cur - o) * (cur - o) - (new - o) * (new - o);
        }
        out.push((improvement, cand as u32, s0, s1));
    }
    out
}

pub fn apply_line(sl: &SourceLines, pic: &mut [f64], s0: usize, s1: usize, strength: f64) {
    for k in s0..s1 {
        let px = sl.flat_idx[k] as usize;
        pic[px] = (pic[px] + strength * sl.val[k]).clamp(0.0, 1.0);
    }
}

/// Offer a candidate to a descending top-W list. Later candidates win ties,
/// which reproduces the greedy `>=` tie-break when W == 1.
pub fn offer_top_w(
    top: &mut Vec<(f64, usize, u32, usize, usize)>,
    item: (f64, usize, u32, usize, usize),
    w: usize,
) {
    if top.len() < w {
        top.push(item);
        top.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
        return;
    }
    let worst = w - 1;
    if item.0 >= top[worst].0 {
        top[worst] = item;
        let mut i = worst;
        while i > 0 && top[i - 1].0 < top[i].0 {
            top.swap(i - 1, i);
            i -= 1;
        }
    }
}

pub fn fork_states(
    sources: &[SourceLines],
    states: &[BeamState],
    top: &[(f64, usize, u32, usize, usize)],
    strength: f64,
) -> Vec<BeamState> {
    let mut next = Vec::with_capacity(top.len());
    for &(total, si, target, s0, s1) in top {
        let parent = &states[si];
        let mut pic = parent.pic.clone();
        apply_line(&sources[parent.current], &mut pic, s0, s1, strength);
        let mut order_seq = parent.order.clone();
        order_seq.push(target as u64);
        next.push(BeamState {
            pic,
            current: target as usize,
            score: total,
            order: order_seq,
        });
    }
    next
}

pub fn best_base_score(states: &[BeamState]) -> f64 {
    states
        .iter()
        .map(|s| s.score)
        .fold(f64::NEG_INFINITY, f64::max)
}

/// Shared parallel line-cache builder (the same rasterizer create_art uses).
pub fn build_cache(nails: &[(i64, i64)], w: usize) -> Vec<SourceLines> {
    let n = nails.len();
    let workers = std::thread::available_parallelism()
        .map(|v| v.get())
        .unwrap_or(1)
        .min(n)
        .max(1);
    let chunk = (n + workers - 1) / workers;
    let mut chunks: Vec<Vec<SourceLines>> = Vec::new();
    std::thread::scope(|scope| {
        let mut handles = Vec::new();
        for start in (0..n).step_by(chunk) {
            let nails_ref = nails;
            handles.push(scope.spawn(move || build_sources(nails_ref, start..(start + chunk).min(n), w)));
        }
        for handle in handles {
            chunks.push(handle.join().expect("line cache worker panicked"));
        }
    });
    let mut sources = Vec::with_capacity(n);
    for mut chunk_sources in chunks {
        sources.append(&mut chunk_sources);
    }
    sources
}

/// Beam search over pull sequences. Width 1 reproduces create_art bit for
/// bit. Larger widths keep W parallel futures competing on cumulative
/// improvement. Returns the best final hypothesis.
pub fn beam_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    strength: f64,
    i_limit: Option<u64>,
    random_nails: Option<u64>,
    white: bool,
    beam: u16,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 {
        return Err("beam_search needs a grayscale target".to_string());
    }
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();
    let width = (beam as usize).max(1);

    let order: Vec<usize> = match random_nails {
        None => (0..n).collect(),
        Some(k) => seeded_subset(n, k as usize, 42),
    };
    let sources = build_cache(&nails, w);

    let mut states = vec![BeamState {
        pic: vec![if white { 1.0 } else { 0.0 }; w * h],
        current: 0,
        score: 0.0,
        order: vec![0],
    }];

    let mut i = 0u64;
    let mut fails = 0u32;

    loop {
        i += 1;
        match i_limit {
            None => {
                if fails >= 3 {
                    break;
                }
            }
            Some(limit) => {
                if i > limit {
                    break;
                }
            }
        }

        let mut top: Vec<(f64, usize, u32, usize, usize)> = Vec::with_capacity(width);
        for (si, state) in states.iter().enumerate() {
            for (imp, target, s0, s1) in
                scan_candidates(&sources, &order, n, &orig.data, strength, state)
            {
                offer_top_w(&mut top, (state.score + imp, si, target, s0, s1), width);
            }
        }

        let best_total = top.first().map(|t| t.0).unwrap_or(f64::NEG_INFINITY);
        if best_total <= best_base_score(&states) {
            fails += 1;
            continue;
        }

        states = fork_states(&sources, &states, &top, strength);
    }

    let best = states
        .iter()
        .max_by(|a, b| a.score.partial_cmp(&b.score).unwrap())
        .unwrap();
    Ok((best.order.clone(), Image { data: best.pic.clone(), w, h, ch: 1 }))
}

/// Receding-horizon search (MPC / rollout style). For every committed pull,
/// expand a beam of `beam` hypotheses for `horizon` steps ahead, then commit
/// only the first pull of the best final hypothesis and slide the horizon.
pub fn horizon_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    strength: f64,
    i_limit: Option<u64>,
    horizon: u32,
    beam: u16,
    random_nails: Option<u64>,
    white: bool,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 {
        return Err("horizon_search needs a grayscale target".to_string());
    }
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();
    let width = (beam as usize).max(1);

    let order: Vec<usize> = match random_nails {
        None => (0..n).collect(),
        Some(k) => seeded_subset(n, k as usize, 42),
    };
    let sources = build_cache(&nails, w);

    let mut pic = vec![if white { 1.0 } else { 0.0 }; w * h];
    let mut pull_order: Vec<u64> = vec![0];
    let mut current = 0usize;

    let mut i = 0u64;
    let mut fails = 0u32;

    loop {
        i += 1;
        match i_limit {
            None => {
                if fails >= 3 {
                    break;
                }
            }
            Some(limit) => {
                if i > limit {
                    break;
                }
            }
        }

        // roll the beam `horizon` steps into the future from (pic, current)
        let mut states = vec![BeamState {
            pic: pic.clone(),
            current,
            score: 0.0,
            order: Vec::new(),
        }];
        for _ in 0..horizon {
            let mut top: Vec<(f64, usize, u32, usize, usize)> = Vec::with_capacity(width);
            for (si, state) in states.iter().enumerate() {
                for (imp, target, s0, s1) in
                    scan_candidates(&sources, &order, n, &orig.data, strength, state)
                {
                    offer_top_w(&mut top, (state.score + imp, si, target, s0, s1), width);
                }
            }
            if top.is_empty() || top[0].0 <= best_base_score(&states) {
                break;
            }
            states = fork_states(&sources, &states, &top, strength);
        }

        let best = states
            .iter()
            .max_by(|a, b| a.score.partial_cmp(&b.score).unwrap())
            .unwrap();
        match best.order.first().copied() {
            Some(target) if best.score > 0.0 => {
                let sl = &sources[current];
                if let Ok(seg) = sl.targets.binary_search(&(target as u32)) {
                    let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
                    apply_line(sl, &mut pic, s0, s1, strength);
                }
                pull_order.push(target);
                current = target as usize;
            }
            _ => {
                fails += 1;
            }
        }
    }

    Ok((pull_order, Image { data: pic, w, h, ch: 1 }))
}


// ---------------------------------------------------------------------------
// Renders (ports of restring.canvas.pull_order_to_array_*)
// ---------------------------------------------------------------------------

pub fn scaled_nails(nails: &[(i64, i64)], x_ratio: f64, y_ratio: f64) -> Vec<(i64, i64)> {
    nails
        .iter()
        .map(|&(r, c)| ((y_ratio * r as f64) as i64, (x_ratio * c as f64) as i64))
        .collect()
}

/// Snapshot an animation of a B/W pull order. `frames == 0` is raw mode: one
/// image after every pull. `frames == n > 0` is downsampled mode: n images,
/// frame 0 the blank canvas, the last frame after the final pull, the rest at
/// evenly spaced pull counts (each pull applied exactly once, none skipped).
/// Accumulate semantics match render_bw, so the last frame is pixel-identical
/// to the full render at the same strength.
pub fn animate_bw(
    order: Vec<u64>,
    nails: Vec<(i64, i64)>,
    strength: f64,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    frames: usize,
) -> Vec<Image> {
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h];
    let total = order.len().saturating_sub(1);
    let mut out: Vec<Image> = Vec::new();

    if frames == 0 {
        for step in 0..total {
            draw_bw_step(&nails, &order, &mut canvas, strength, step, out_w, out_h);
            out.push(snapshot(&canvas, out_w, out_h, 1));
        }
        return out;
    }
    if frames == 1 {
        out.push(snapshot(&canvas, out_w, out_h, 1));
        return out;
    }

    let f = frames as u64;
    out.push(snapshot(&canvas, out_w, out_h, 1));
    let mut done = 0usize;
    for i in 1..f {
        let target = ((total as u64 * i as u64) / (f - 1)) as usize;
        while done < target {
            draw_bw_step(&nails, &order, &mut canvas, strength, done, out_w, out_h);
            done += 1;
        }
        out.push(snapshot(&canvas, out_w, out_h, 1));
    }
    out
}

/// Snapshot an animation of interleaved RGB pull orders: each interleaved
/// step paints one pull of every channel (the render_rgb contract), frames
/// follow the same raw/downsampled split as animate_bw.
pub fn animate_rgb(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    frames: usize,
) -> Result<Vec<Image>, String> {
    if strengths.len() != orders.len() {
        return Err("animate_rgb needs one strength per channel order".to_string());
    }
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    let colors: [[f64; 3]; 3] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h * 3];
    let total = orders.first().map(|o| o.len().saturating_sub(1)).unwrap_or(0);
    let mut out: Vec<Image> = Vec::new();

    let draw_step = |canvas: &mut [f64], step: usize| {
        for (color_idx, order) in orders.iter().enumerate() {
            let (a, b) = (order[step] as usize, order[step + 1] as usize);
            let (rr, cc, val) = zingl_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1);
            for k in 0..rr.len() {
                let px = (rr[k] as usize * out_w + cc[k] as usize).min(out_w * out_h - 1);
                for c in 0..3 {
                    canvas[px * 3 + c] += colors[color_idx][c] * val[k] * strengths[color_idx];
                }
            }
        }
    };

    if frames == 0 {
        for step in 0..total {
            draw_step(&mut canvas, step);
            out.push(snapshot(&canvas, out_w, out_h, 3));
        }
        return Ok(out);
    }
    if frames == 1 {
        out.push(snapshot(&canvas, out_w, out_h, 3));
        return Ok(out);
    }

    let f = frames as u64;
    out.push(snapshot(&canvas, out_w, out_h, 3));
    let mut done = 0usize;
    for i in 1..f {
        let target = ((total as u64 * i as u64) / (f - 1)) as usize;
        while done < target {
            draw_step(&mut canvas, done);
            done += 1;
        }
        out.push(snapshot(&canvas, out_w, out_h, 3));
    }
    Ok(out)
}

/// Clamp a running canvas into an Image snapshot.
pub fn snapshot(canvas: &[f64], w: usize, h: usize, ch: usize) -> Image {
    Image {
        data: canvas.iter().map(|v| v.clamp(0.0, 1.0)).collect(),
        w,
        h,
        ch,
    }
}

pub fn draw_bw_step(
    nails: &[(i64, i64)],
    order: &[u64],
    canvas: &mut [f64],
    strength: f64,
    step: usize,
    out_w: usize,
    out_h: usize,
) {
    let (a, b) = (order[step] as usize, order[step + 1] as usize);
    let (rr, cc, val) = zingl_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1);
    for k in 0..rr.len() {
        let idx = (rr[k] as usize * out_w + cc[k] as usize).min(out_w * out_h - 1);
        canvas[idx] += val[k] * strength;
    }
}

/// Encode frames as an animated GIF (image crate GIF encoder, infinite loop,
/// full-canvas frames so disposal semantics do not matter). Returns the
/// number of frames written.
pub fn save_gif(path: &str, images: &[Image], fps: u16) -> Result<usize, String> {
    use image::codecs::gif::{GifEncoder, Repeat};

    let file = std::fs::File::create(path).map_err(|e| format!("cannot create {path}: {e}"))?;
    let mut encoder = GifEncoder::new(file);
    encoder
        .set_repeat(Repeat::Infinite)
        .map_err(|e| format!("gif encoder setup failed: {e}"))?;
    let delay_num = 1000u32 / fps.max(1) as u32;
    let delay = image::Delay::from_numer_denom_ms(delay_num, 1);
    for img in images.iter() {
        let mut rgba = Vec::with_capacity(img.w * img.h * 4);
        match img.ch {
            1 => {
                for &v in &img.data {
                    let x = (v.clamp(0.0, 1.0) * 255.0).round() as u8;
                    rgba.extend_from_slice(&[x, x, x, 255]);
                }
            }
            3 => {
                for px in img.data.chunks_exact(3) {
                    for c in px {
                        rgba.push((c.clamp(0.0, 1.0) * 255.0).round() as u8);
                    }
                    rgba.push(255);
                }
            }
            _ => {
                return Err("save_gif supports 1-channel and 3-channel images".to_string());
            }
        }
        let buffer = image::RgbaImage::from_raw(img.w as u32, img.h as u32, rgba)
            .ok_or_else(|| "frame buffer size mismatch".to_string())?;
        encoder
            .encode_frame(image::Frame::from_parts(buffer, 0, 0, delay))
            .map_err(|e| format!("gif encode failed: {e}"))?;
    }
    Ok(images.len())
}

/// Sobel gradient magnitude (grayscale; color images collapse through the
/// standard luminance weights first). Exposed for placement analysis and
/// future tasks; pure f64 convolution with clamped edges.
pub fn gradient_magnitude(img: &Image) -> Image {
    let (w, h) = (img.w, img.h);
    let gray: Vec<f64> = if img.ch == 1 {
        img.data.clone()
    } else {
        img.data
            .chunks_exact(3)
            .map(|px| 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2])
            .collect()
    };
    const KX: [[f64; 3]; 3] = [[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]];
    const KY: [[f64; 3]; 3] = [[-1.0, -2.0, -1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]];
    let mut mag = vec![0.0; w * h];
    for r in 0..h {
        for c in 0..w {
            let mut gx = 0.0f64;
            let mut gy = 0.0f64;
            for dr in 0..3 {
                for dc in 0..3 {
                    let rr = (r as i64 + dr as i64 - 1).clamp(0, h as i64 - 1) as usize;
                    let cc = (c as i64 + dc as i64 - 1).clamp(0, w as i64 - 1) as usize;
                    let v = gray[rr * w + cc];
                    gx += KX[dr][dc] * v;
                    gy += KY[dr][dc] * v;
                }
            }
            mag[r * w + c] = (gx * gx + gy * gy).sqrt();
        }
    }
    Image { data: mag, w, h, ch: 1 }
}

/// One anti-aliased thick segment. Pixel centers sit at integer coordinates
/// (the convention zingl_line draws with); coverage = clamp(1 - (distance to
/// segment - half_width), 0, 1), a 1-px linear falloff in the same spirit as
/// the Zingl AA. Returns (rows, cols, coverage); indices may fall outside a
/// canvas near the edges, callers clamp when stamping. Exposed as
/// _core.thick_line for golden tests, mirroring line_aa.
pub fn thick_line(r0: i64, c0: i64, r1: i64, c1: i64, half_width: f64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    let (ay, ax) = (r0 as f64, c0 as f64);
    let (dry, dcx) = ((r1 - r0) as f64, (c1 - c0) as f64);
    let len2 = dry * dry + dcx * dcx;
    let reach = (half_width + 1.0).ceil() as i64;
    let mut rr = Vec::new();
    let mut cc = Vec::new();
    let mut cov = Vec::new();
    for r in (r0.min(r1) - reach)..=(r0.max(r1) + reach) {
        for c in (c0.min(c1) - reach)..=(c0.max(c1) + reach) {
            let (py, px) = (r as f64, c as f64);
            let t = if len2 > 0.0 {
                (((py - ay) * dry + (px - ax) * dcx) / len2).clamp(0.0, 1.0)
            } else {
                0.0
            };
            let (cy, cx) = (ay + t * dry, ax + t * dcx);
            let dist = ((py - cy) * (py - cy) + (px - cx) * (px - cx)).sqrt();
            let coverage = (1.0 - (dist - half_width)).clamp(0.0, 1.0);
            if coverage > 0.0 {
                rr.push(r);
                cc.push(c);
                cov.push(coverage);
            }
        }
    }
    (rr, cc, cov)
}

/// Physical thread model: render with segments of the given pixel width
/// (thread_px), drop-in parallel of render_bw with thick stamping. Same
/// accumulation and end-clamp semantics.
pub fn render_bw_thick(
    order: Vec<u64>,
    nails: Vec<(i64, i64)>,
    strength: f64,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    thread_px: f64,
) -> Image {
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    let half_width = thread_px / 2.0;
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h];
    for pair in order.windows(2) {
        let (a, b) = (pair[0] as usize, pair[1] as usize);
        let (rr, cc, cov) = thick_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1, half_width);
        for k in 0..rr.len() {
            let r = rr[k].clamp(0, out_h as i64 - 1) as usize;
            let c = cc[k].clamp(0, out_w as i64 - 1) as usize;
            canvas[r * out_w + c] += cov[k] * strength;
        }
    }
    for v in canvas.iter_mut() {
        *v = v.clamp(0.0, 1.0);
    }
    Image { data: canvas, w: out_w, h: out_h, ch: 1 }
}

/// Physical thread model for interleaved RGB pull orders, parallel of
/// render_rgb with thick stamping.
pub fn render_rgb_thick(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    thread_px: f64,
) -> Result<Image, String> {
    if strengths.len() != orders.len() {
        return Err("render_rgb_thick needs one strength per channel order".to_string());
    }
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    let colors: [[f64; 3]; 3] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
    let half_width = thread_px / 2.0;
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h * 3];
    for step in 0..orders.first().map(|o| o.len().saturating_sub(1)).unwrap_or(0) {
        for (color_idx, order) in orders.iter().enumerate() {
            let (a, b) = (order[step] as usize, order[step + 1] as usize);
            let (rr, cc, cov) = thick_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1, half_width);
            for k in 0..rr.len() {
                let r = rr[k].clamp(0, out_h as i64 - 1) as usize;
                let c = cc[k].clamp(0, out_w as i64 - 1) as usize;
                for ch in 0..3 {
                    canvas[(r * out_w + c) * 3 + ch] += colors[color_idx][ch] * cov[k] * strengths[color_idx];
                }
            }
        }
    }
    for v in canvas.iter_mut() {
        *v = v.clamp(0.0, 1.0);
    }
    Ok(Image { data: canvas, w: out_w, h: out_h, ch: 3 })
}

/// Render a B/W pull order at the given resolution (port of
/// canvas.pull_order_to_array_bw; nail scaling included).
pub fn render_bw(
    order: Vec<u64>,
    nails: Vec<(i64, i64)>,
    strength: f64,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
) -> Image {
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h];
    for pair in order.windows(2) {
        let (a, b) = (pair[0] as usize, pair[1] as usize);
        let (rr, cc, val) = zingl_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1);
        for k in 0..rr.len() {
            let idx = (rr[k] as usize * out_w + cc[k] as usize).min(canvas.len() - 1);
            canvas[idx] += val[k] * strength;
        }
    }
    for v in canvas.iter_mut() {
        *v = v.clamp(0.0, 1.0);
    }
    Image { data: canvas, w: out_w, h: out_h, ch: 1 }
}

/// Shared accumulation for palette renders: one interleaved pass over the
/// per-thread orders, each thread adding its color * strength per touched
/// pixel, clamp at the end. The loop structure and arithmetic are identical
/// to the original render_rgb.
pub fn render_palette_impl(
    orders: &[Vec<u64>],
    nails: &[(i64, i64)],
    colors: &[(f64, f64, f64)],
    strengths: &[f64],
    out_w: usize,
    out_h: usize,
    white: bool,
) -> Image {
    let color_triples: Vec<[f64; 3]> = colors.iter().map(|c| [c.0, c.1, c.2]).collect();
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h * 3];
    let pulls = orders.first().map(|o| o.len().saturating_sub(1)).unwrap_or(0);
    for step in 0..pulls {
        for (color_idx, order) in orders.iter().enumerate() {
            let (a, b) = (order[step] as usize, order[step + 1] as usize);
            let (rr, cc, val) = zingl_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1);
            for k in 0..rr.len() {
                let px = (rr[k] as usize * out_w + cc[k] as usize).min(out_w * out_h - 1);
                for c in 0..3 {
                    canvas[px * 3 + c] += color_triples[color_idx][c] * val[k] * strengths[color_idx];
                }
            }
        }
    }
    for v in canvas.iter_mut() {
        *v = v.clamp(0.0, 1.0);
    }
    Image { data: canvas, w: out_w, h: out_h, ch: 3 }
}

/// Render interleaved RGB pull orders (port of canvas.pull_order_to_array_rgb).
/// Thin wrapper over render_palette with the fixed compatibility triple.
pub fn render_rgb(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
) -> Result<Image, String> {
    if strengths.len() != orders.len() {
        return Err("render_rgb needs one strength per channel order".to_string());
    }
    let colors = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)];
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    Ok(render_palette_impl(&orders, &nails, &colors, &strengths, out_w, out_h, white))
}

/// Render interleaved pull orders for an arbitrary thread palette: one color
/// triple per order, additive-on-white (each thread darkens the channels it
/// carries). With `thread_px` set, segments stamp with the physical width.
pub fn render_palette(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    colors: Vec<(f64, f64, f64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    thread_px: Option<f64>,
) -> Result<Image, String> {
    if colors.len() != orders.len() || strengths.len() != orders.len() {
        return Err("render_palette needs one color and one strength per order".to_string());
    }
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    if thread_px.is_none() {
        return Ok(render_palette_impl(&orders, &nails, &colors, &strengths, out_w, out_h, white));
    }
    let half_width = thread_px.unwrap() / 2.0;
    let color_triples: Vec<[f64; 3]> = colors.iter().map(|c| [c.0, c.1, c.2]).collect();
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h * 3];
    let pulls = orders.first().map(|o| o.len().saturating_sub(1)).unwrap_or(0);
    for step in 0..pulls {
        for (color_idx, order) in orders.iter().enumerate() {
            let (a, b) = (order[step] as usize, order[step + 1] as usize);
            let (rr, cc, cov) = thick_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1, half_width);
            for k in 0..rr.len() {
                let r = rr[k].clamp(0, out_h as i64 - 1) as usize;
                let c = cc[k].clamp(0, out_w as i64 - 1) as usize;
                for ch in 0..3 {
                    canvas[(r * out_w + c) * 3 + ch] +=
                        color_triples[color_idx][ch] * cov[k] * strengths[color_idx];
                }
            }
        }
    }
    for v in canvas.iter_mut() {
        *v = v.clamp(0.0, 1.0);
    }
    Ok(Image { data: canvas, w: out_w, h: out_h, ch: 3 })
}

// ---------------------------------------------------------------------------
// Metrics (ports of restring.metrics)
// ---------------------------------------------------------------------------

pub fn mse(a: &Image, b: &Image) -> Result<f64, String> {
    same_shape(a, b)?;
    Ok(a.data.iter().zip(&b.data).map(|(x, y)| (x - y) * (x - y)).sum::<f64>() / a.data.len() as f64)
}

/// SSIM after a box blur on both images: thin dark lines on white defeat
/// plain SSIM's local statistics; the blur restores them (T-16, see
/// docs/research/pull-count-quality.md). Grayscale input required.
pub fn ssim_blur(a: &Image, b: &Image, radius: usize) -> Result<f64, String> {
    same_shape(a, b)?;
    ssim(&a.box_blur(radius), &b.box_blur(radius))
}

pub fn corr(a: &Image, b: &Image) -> Result<f64, String> {
    same_shape(a, b)?;
    let (ma, mb): (f64, f64) = (
        a.data.iter().sum::<f64>() / a.data.len() as f64,
        b.data.iter().sum::<f64>() / b.data.len() as f64,
    );
    let mut num = 0.0;
    let mut da = 0.0;
    let mut db = 0.0;
    for (&x, &y) in a.data.iter().zip(&b.data) {
        num += (x - ma) * (y - mb);
        da += (x - ma) * (x - ma);
        db += (y - mb) * (y - mb);
    }
    Ok(num / (da * db).sqrt())
}

pub fn ssim(a: &Image, b: &Image) -> Result<f64, String> {
    same_shape(a, b)?;
    if a.ch != 1 {
        return Err("ssim needs grayscale images".to_string());
    }
    let (w, h) = (a.w, a.h);
    let win = 7usize;
    if w < win || h < win {
        return Err("image smaller than the SSIM window".to_string());
    }
    let c1 = 0.01f64 * 0.01;
    let c2 = 0.03f64 * 0.03;
    let win_area = (win * win) as f64;

    // integral images
    let mut ia = vec![0.0f64; (w + 1) * (h + 1)];
    let mut ib = vec![0.0f64; (w + 1) * (h + 1)];
    let mut iaa = vec![0.0f64; (w + 1) * (h + 1)];
    let mut ibb = vec![0.0f64; (w + 1) * (h + 1)];
    let mut iab = vec![0.0f64; (w + 1) * (h + 1)];
    for r in 0..h {
        for c in 0..w {
            let (idx, up) = ((r + 1) * (w + 1) + c + 1, r * (w + 1) + c + 1);
            let (x, y) = (a.data[r * w + c], b.data[r * w + c]);
            ia[idx] = ia[up] + ia[(r + 1) * (w + 1) + c] - ia[r * (w + 1) + c] + x;
            ib[idx] = ib[up] + ib[(r + 1) * (w + 1) + c] - ib[r * (w + 1) + c] + y;
            iaa[idx] = iaa[up] + iaa[(r + 1) * (w + 1) + c] - iaa[r * (w + 1) + c] + x * x;
            ibb[idx] = ibb[up] + ibb[(r + 1) * (w + 1) + c] - ibb[r * (w + 1) + c] + y * y;
            iab[idx] = iab[up] + iab[(r + 1) * (w + 1) + c] - iab[r * (w + 1) + c] + x * y;
        }
    }
    let win_sum = |ii: &Vec<f64>, r0: usize, c0: usize| -> f64 {
        let (r1, c1) = (r0 + win, c0 + win);
        ii[r1 * (w + 1) + c1] - ii[r0 * (w + 1) + c1] - ii[r1 * (w + 1) + c0] + ii[r0 * (w + 1) + c0]
    };

    let mut total = 0.0;
    let mut count = 0usize;
    for r0 in 0..=h - win {
        for c0 in 0..=w - win {
            let mu_a = win_sum(&ia, r0, c0) / win_area;
            let mu_b = win_sum(&ib, r0, c0) / win_area;
            let var_a = win_sum(&iaa, r0, c0) / win_area - mu_a * mu_a;
            let var_b = win_sum(&ibb, r0, c0) / win_area - mu_b * mu_b;
            let cov = win_sum(&iab, r0, c0) / win_area - mu_a * mu_b;
            let num = (2.0 * mu_a * mu_b + c1) * (2.0 * cov + c2);
            let den = (mu_a * mu_a + mu_b * mu_b + c1) * (var_a + var_b + c2);
            total += num / den;
            count += 1;
        }
    }
    Ok(total / count as f64)
}

pub fn same_shape(a: &Image, b: &Image) -> Result<(), String> {
    if a.w != b.w || a.h != b.h || a.ch != b.ch {
        return Err("metric needs same-shape images".to_string());
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Experimental: alternatives to plain greedy (importance, asymmetric,
// multi-scale, add/remove local search)
// ---------------------------------------------------------------------------

/// Scan with a per-pixel weight map. The improvement of each candidate pull
/// is multiplied by the weight of each pixel, concentrating threads where
/// the weight is high.
pub fn scan_candidates_weighted(
    sources: &[SourceLines],
    order: &[usize],
    n: usize,
    orig: &[f64],
    weights: &[f64],
    strength: f64,
    state: &BeamState,
) -> Vec<(f64, u32, usize, usize)> {
    let sl = &sources[state.current];
    let mut out = Vec::with_capacity(order.len());
    for &cand in order {
        if cand == state.current || cand >= n {
            continue;
        }
        let seg = match sl.targets.binary_search(&(cand as u32)) {
            Ok(pos) => pos,
            Err(_) => continue,
        };
        let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
        let mut improvement = 0.0f64;
        for k in s0..s1 {
            let px = sl.flat_idx[k] as usize;
            let cur = state.pic[px];
            let new = (cur + strength * sl.val[k]).clamp(0.0, 1.0);
            let o = orig[px];
            improvement += weights[px] * ((cur - o) * (cur - o) - (new - o) * (new - o));
        }
        out.push((improvement, cand as u32, s0, s1));
    }
    out
}

/// Gaussian center-focus weight map for importance-weighted search:
/// w(r,c) = bg + (peak - bg) * exp(-d^2 / (2 sigma^2)), d = pixel distance
/// from the image center (w/2, h/2). Matches the numpy builder in
/// scripts/alternatives_experiment.py.
pub fn gaussian_weights(w: usize, h: usize, sigma: f64, peak: f64, bg: f64) -> Image {
    let (cy, cx) = (h as f64 / 2.0, w as f64 / 2.0);
    let mut data = Vec::with_capacity(w * h);
    for r in 0..h {
        let dr = r as f64 - cy;
        for c in 0..w {
            let dc = c as f64 - cx;
            let gauss = (-(dr * dr + dc * dc) / (2.0 * sigma * sigma)).exp();
            data.push(bg + (peak - bg) * gauss);
        }
    }
    Image { data, w, h, ch: 1 }
}

/// Importance-weighted greedy search. Same pipeline as create_art, but each
/// pixel's error contribution is multiplied by a weight. Higher weights
/// attract more threads to the region.
///
/// Superseded: create_art with weights=Some(map) carries the same scoring in
/// the production path, with the parallel cache build and random_nails.
/// Kept because scripts/alternatives_experiment.py calls this function.
pub fn weighted_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    weights: &Image,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 || weights.ch != 1 {
        return Err("weighted_search needs grayscale images".to_string());
    }
    if orig.w != weights.w || orig.h != weights.h {
        return Err("orig and weights must have the same shape".to_string());
    }
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();
    let order: Vec<usize> = (0..n).collect();
    let sources = build_cache(&nails, w);

    let mut state = BeamState {
        pic: vec![if white { 1.0 } else { 0.0 }; w * h],
        current: 0,
        score: 0.0,
        order: vec![0],
    };

    let mut i = 0u64;
    let mut fails = 0u32;
    loop {
        i += 1;
        match i_limit {
            None => { if fails >= 3 { break; } }
            Some(limit) => { if i > limit { break; } }
        }

        let mut best: (f64, u32, usize, usize) = (f64::NEG_INFINITY, 0, 0, 0);
        for (imp, target, s0, s1) in scan_candidates_weighted(
            &sources, &order, n, &orig.data, &weights.data, strength, &state,
        ) {
            if imp >= best.0 {
                best = (imp, target, s0, s1);
            }
        }
        if best.0 <= 0.0 { fails += 1; continue; }

        state.order.push(best.1 as u64);
        apply_line(&sources[state.current], &mut state.pic, best.2, best.3, strength);
        state.current = best.1 as usize;
    }
    Ok((state.order, Image { data: state.pic, w, h, ch: 1 }))
}

/// Scan with asymmetric error penalties. Over-darkening (new < orig) is
/// penalized alpha times more than under-darkening.
pub fn scan_candidates_asymmetric(
    sources: &[SourceLines],
    order: &[usize],
    n: usize,
    orig: &[f64],
    alpha: f64,
    strength: f64,
    state: &BeamState,
) -> Vec<(f64, u32, usize, usize)> {
    let sl = &sources[state.current];
    let mut out = Vec::with_capacity(order.len());
    let penalty = |diff: f64, alpha: f64| -> f64 {
        if diff < 0.0 { alpha * diff * diff } else { diff * diff }
    };
    for &cand in order {
        if cand == state.current || cand >= n {
            continue;
        }
        let seg = match sl.targets.binary_search(&(cand as u32)) {
            Ok(pos) => pos,
            Err(_) => continue,
        };
        let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
        let mut improvement = 0.0f64;
        for k in s0..s1 {
            let px = sl.flat_idx[k] as usize;
            let cur = state.pic[px];
            let new = (cur + strength * sl.val[k]).clamp(0.0, 1.0);
            let o = orig[px];
            improvement += penalty(cur - o, alpha) - penalty(new - o, alpha);
        }
        out.push((improvement, cand as u32, s0, s1));
    }
    out
}

/// Asymmetric-penalty greedy search. Over-darkening costs alpha times more
/// than under-darkening, preserving bright details.
pub fn asymmetric_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    alpha: f64,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 {
        return Err("asymmetric_search needs a grayscale target".to_string());
    }
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();
    let order: Vec<usize> = (0..n).collect();
    let sources = build_cache(&nails, w);

    let mut state = BeamState {
        pic: vec![if white { 1.0 } else { 0.0 }; w * h],
        current: 0,
        score: 0.0,
        order: vec![0],
    };

    let mut i = 0u64;
    let mut fails = 0u32;
    loop {
        i += 1;
        match i_limit {
            None => { if fails >= 3 { break; } }
            Some(limit) => { if i > limit { break; } }
        }

        let mut best: (f64, u32, usize, usize) = (f64::NEG_INFINITY, 0, 0, 0);
        for (imp, target, s0, s1) in scan_candidates_asymmetric(
            &sources, &order, n, &orig.data, alpha, strength, &state,
        ) {
            if imp >= best.0 {
                best = (imp, target, s0, s1);
            }
        }
        if best.0 <= 0.0 { fails += 1; continue; }

        state.order.push(best.1 as u64);
        apply_line(&sources[state.current], &mut state.pic, best.2, best.3, strength);
        state.current = best.1 as usize;
    }
    Ok((state.order, Image { data: state.pic, w, h, ch: 1 }))
}

/// Greedy search starting from an existing canvas state (for multi-scale).
/// The initial canvas is the result of a previous coarse pass.
pub fn create_art_from(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    initial_pic: &Image,
    strength: f64,
    i_limit: Option<u64>,
    _white: bool,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 || initial_pic.ch != 1 {
        return Err("create_art_from needs grayscale images".to_string());
    }
    if orig.w != initial_pic.w || orig.h != initial_pic.h {
        return Err("orig and initial_pic must have the same shape".to_string());
    }
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();
    let order: Vec<usize> = (0..n).collect();
    let sources = build_cache(&nails, w);

    let mut state = BeamState {
        pic: initial_pic.data.clone(),
        current: 0,
        score: 0.0,
        order: vec![0],
    };

    let mut i = 0u64;
    let mut fails = 0u32;
    loop {
        i += 1;
        match i_limit {
            None => { if fails >= 3 { break; } }
            Some(limit) => { if i > limit { break; } }
        }

        let mut best: (f64, u32, usize, usize) = (f64::NEG_INFINITY, 0, 0, 0);
        for (imp, target, s0, s1) in scan_candidates(
            &sources, &order, n, &orig.data, strength, &state,
        ) {
            if imp >= best.0 {
                best = (imp, target, s0, s1);
            }
        }
        if best.0 <= 0.0 { fails += 1; continue; }

        state.order.push(best.1 as u64);
        apply_line(&sources[state.current], &mut state.pic, best.2, best.3, strength);
        state.current = best.1 as usize;
    }
    Ok((state.order, Image { data: state.pic, w, h, ch: 1 }))
}

/// Add/remove local search on a completed pull order. For `sweeps` rounds:
/// try removing each pull (rebuild canvas without it), keep removals that
/// improve MSE. Then try adding the best new pull at each gap position.
pub fn local_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    pull_order: Vec<u64>,
    strength: f64,
    sweeps: u32,
) -> Result<(Vec<u64>, Image), String> {
    if orig.ch != 1 {
        return Err("local_search needs a grayscale target".to_string());
    }
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();
    let sources = build_cache(&nails, w);
    let order: Vec<usize> = (0..n).collect();

    let mut current_order = pull_order;

    let canvas_mse = |order: &[u64]| -> f64 {
        let mut pic = vec![1.0f64; w * h];
        let mut current = order[0] as usize;
        for &target in &order[1..] {
            let sl = &sources[current];
            if let Ok(seg) = sl.targets.binary_search(&(target as u32)) {
                let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
                apply_line(sl, &mut pic, s0, s1, strength);
            }
            current = target as usize;
        }
        let mut sum = 0.0;
        for px in 0..w * h {
            let d = pic[px] - orig.data[px];
            sum += d * d;
        }
        sum
    };

    for _sweep in 0..sweeps {
        let baseline = canvas_mse(&current_order);
        let mut improved = false;

        // removal pass: try dropping each pull (except the first anchor)
        let mut i = 1;
        while i < current_order.len() {
            let mut trial = current_order.clone();
            trial.remove(i);
            let trial_mse = canvas_mse(&trial);
            if trial_mse < baseline * 0.9999 {
                current_order = trial;
                improved = true;
                // don't advance i, try removing the next one at same position
            } else {
                i += 1;
            }
        }

        // addition pass: find the best pull to append
        let pic_after = {
            let mut pic = vec![1.0f64; w * h];
            let mut current = current_order[0] as usize;
            for &target in &current_order[1..] {
                let sl = &sources[current];
                if let Ok(seg) = sl.targets.binary_search(&(target as u32)) {
                    let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
                    apply_line(sl, &mut pic, s0, s1, strength);
                }
                current = target as usize;
            }
            pic
        };
        let state = BeamState { pic: pic_after, current: current_order.last().copied().unwrap_or(0) as usize, score: 0.0, order: Vec::new() };
        let mut best: (f64, u32) = (f64::NEG_INFINITY, 0);
        for (imp, target, _, _) in scan_candidates(&sources, &order, n, &orig.data, strength, &state) {
            if imp > best.0 {
                best = (imp, target);
            }
        }
        if best.0 > 0.0 {
            current_order.push(best.1 as u64);
            improved = true;
        }

        if !improved {
            break;
        }
    }

    // rebuild final canvas
    let mut pic = vec![1.0f64; w * h];
    let mut current = current_order[0] as usize;
    for &target in &current_order[1..] {
        let sl = &sources[current];
        if let Ok(seg) = sl.targets.binary_search(&(target as u32)) {
            let (s0, s1) = (sl.bounds[seg], sl.bounds[seg + 1]);
            apply_line(sl, &mut pic, s0, s1, strength);
        }
        current = target as usize;
    }
    Ok((current_order, Image { data: pic, w, h, ch: 1 }))
}


/// Line cache for all nails: thread-parallel split on native targets, serial
/// on wasm (std::thread::scope is unavailable there).
pub fn build_line_cache(nails: &[(i64, i64)], w: usize, n: usize) -> Vec<SourceLines> {
    #[cfg(not(target_family = "wasm"))]
    {
        let workers = std::thread::available_parallelism()
            .map(|v| v.get())
            .unwrap_or(1)
            .min(n)
            .max(1);
        let chunk = (n + workers - 1) / workers;
        let mut chunks: Vec<Vec<SourceLines>> = Vec::new();
        std::thread::scope(|scope| {
            let mut handles = Vec::new();
            for start in (0..n).step_by(chunk) {
                handles.push(scope.spawn(move || build_sources(nails, start..(start + chunk).min(n), w)));
            }
            for handle in handles {
                chunks.push(handle.join().expect("line cache worker panicked"));
            }
        });
        let mut sources = Vec::with_capacity(n);
        for mut chunk_sources in chunks {
            sources.append(&mut chunk_sources);
        }
        sources
    }
    #[cfg(target_family = "wasm")]
    {
        build_sources(nails, 0..n, w)
    }
}

