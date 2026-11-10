//! Rust core for ReString: image container and codecs, nail layouts, the
//! Zingl anti-aliased line rasterizer, the greedy pull-order search and the
//! thread renders — everything the Python package needs at runtime, so the
//! package itself has zero Python dependencies.
//!
//! All algorithms are one-to-one ports of the Python reference
//! implementations in restring.{canvas,nails,image_transformations,metrics}.

use std::collections::HashSet;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// Image container
// ---------------------------------------------------------------------------

#[pyclass]
struct Image {
    data: Vec<f64>, // row-major, ch interleaved
    w: usize,
    h: usize,
    ch: usize,
}

impl Image {
    fn at(&self, r: usize, c: usize, k: usize) -> f64 {
        self.data[(r * self.w + c) * self.ch + k]
    }
    fn set(&mut self, r: usize, c: usize, k: usize, v: f64) {
        let idx = (r * self.w + c) * self.ch + k;
        self.data[idx] = v;
    }
}

#[pymethods]
impl Image {
    /// Load a PNG/JPEG file as an RGB float image in [0, 1].
    #[staticmethod]
    fn load(path: String) -> PyResult<Self> {
        let opened = image::ImageReader::open(&path)
            .map_err(|e| PyValueError::new_err(format!("cannot open {path}: {e}")))?
            .decode()
            .map_err(|e| PyValueError::new_err(format!("cannot decode {path}: {e}")))?;
        let rgb = opened.to_rgb8();
        let (w, h) = rgb.dimensions();
        let data = rgb.into_raw().iter().map(|&b| b as f64 / 255.0).collect();
        Ok(Image { data, w: w as usize, h: h as usize, ch: 3 })
    }

    /// Uniform canvas of the given value (1.0 = white, 0.0 = black).
    #[staticmethod]
    fn blank(w: usize, h: usize, ch: usize, value: f64) -> Self {
        Image { data: vec![value; w * h * ch], w, h, ch }
    }

    /// Build from nested lists: h x w (gray) or h x w x 3 (RGB).
    #[staticmethod]
    fn from_nested(rows: &Bound<'_, PyAny>) -> PyResult<Self> {
        let outer: Vec<Vec<f64>> = if let Ok(flat) = rows.extract::<Vec<Vec<f64>>>() {
            flat // h x w gray
        } else {
            let nested: Vec<Vec<Vec<f64>>> = rows.extract()?;
            let h = nested.len();
            let w = nested.first().map(|r| r.len()).unwrap_or(0);
            let ch = nested.first().and_then(|r| r.first()).map(|p| p.len()).unwrap_or(0);
            let mut flat = Vec::with_capacity(h * w * ch);
            for row in &nested {
                for px in row {
                    if px.len() != ch {
                        return Err(PyValueError::new_err("ragged nested image"));
                    }
                    flat.extend_from_slice(px);
                }
            }
            let img = Image { data: flat, w, h, ch };
            return Ok(img);
        };
        let h = outer.len();
        let w = outer.first().map(|r| r.len()).unwrap_or(0);
        let mut data = Vec::with_capacity(h * w);
        for row in &outer {
            if row.len() != w {
                return Err(PyValueError::new_err("ragged nested image"));
            }
            data.extend_from_slice(row);
        }
        Ok(Image { data, w, h, ch: 1 })
    }

    fn shape(&self) -> (usize, usize, usize) {
        (self.h, self.w, self.ch)
    }

    fn pixel(&self, r: usize, c: usize, k: usize) -> PyResult<f64> {
        if r >= self.h || c >= self.w || k >= self.ch {
            return Err(PyValueError::new_err("pixel index out of range"));
        }
        Ok(self.at(r, c, k))
    }

    fn tolist(&self) -> PyObject {
        Python::with_gil(|py| {
            let mut rows = Vec::with_capacity(self.h);
            for r in 0..self.h {
                let mut row: Vec<PyObject> = Vec::with_capacity(self.w);
                for c in 0..self.w {
                    if self.ch == 1 {
                        row.push(self.at(r, c, 0).into_py(py));
                    } else {
                        let px: Vec<f64> = (0..self.ch).map(|k| self.at(r, c, k)).collect();
                        row.push(px.into_py(py));
                    }
                }
                rows.push(row);
            }
            rows.into_py(py)
        })
    }

    /// Central largest square crop (port of image_transformations.largest_square).
    fn largest_square(&self) -> Self {
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
    fn resize(&self, out_w: usize, out_h: usize) -> Self {
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
    fn gray(&self, scale: f64) -> PyResult<Self> {
        if self.ch != 3 {
            return Err(PyValueError::new_err("gray() needs an RGB image"));
        }
        let mut data = Vec::with_capacity(self.w * self.h);
        for px in self.data.chunks_exact(3) {
            data.push((0.2989 * px[0] + 0.5870 * px[1] + 0.1140 * px[2]) * scale);
        }
        Ok(Image { data, w: self.w, h: self.h, ch: 1 })
    }

    /// Single channel of an RGB image as a gray image.
    fn channel(&self, k: usize) -> PyResult<Self> {
        if k >= self.ch {
            return Err(PyValueError::new_err("channel index out of range"));
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
    fn save_png(&self, path: String) -> PyResult<()> {
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
        result.map_err(|e| PyValueError::new_err(format!("cannot save {path}: {e}")))
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

fn zingl_line(r0: i64, c0: i64, r1: i64, c1: i64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
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
#[pyfunction]
fn line_aa(r0: i64, c0: i64, r1: i64, c1: i64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    zingl_line(r0, c0, r1, c1)
}

// ---------------------------------------------------------------------------
// Nail layouts (ports of restring.nails)
// ---------------------------------------------------------------------------

/// Midpoint ellipse boundary — pixel-set identical to the Python port.
fn ellipse_perimeter(cr: i64, cc_: i64, r_radius: i64, c_radius: i64) -> Vec<(i64, i64)> {
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
#[pyfunction]
fn circle_nails(w: usize, h: usize, nail_step: usize, r1_mult: f64, r2_mult: f64) -> Vec<(i64, i64)> {
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
#[pyfunction]
fn rect_nails(w: usize, h: usize, nail_step: usize) -> Vec<(i64, i64)> {
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

struct SourceLines {
    flat_idx: Vec<u32>,
    val: Vec<f64>,
    bounds: Vec<usize>,
    targets: Vec<u32>,
}

/// Deterministic splitmix64 — self-contained seeded RNG (no external crates).
struct SplitMix64(u64);

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
fn seeded_subset(n: usize, k: usize, seed: u64) -> Vec<usize> {
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
fn build_sources(nails: &[(i64, i64)], range: std::ops::Range<usize>, w: usize) -> Vec<SourceLines> {
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
fn seg_improvement(
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
fn log_debug(py: Python<'_>, msg: &str) {
    let _ = py.import("logging").and_then(|log| {
        let logger = log.call_method1("getLogger", ("restring.core",))?;
        logger.call_method1("debug", (msg,))
    });
}

/// Greedy pull-order search on the given grayscale target. Returns the pull
/// order and the final working canvas. With `random_nails = Some(k)` only a
/// fixed seeded subset of k candidates is scanned each iteration. With
/// `weights = Some(map)` each pixel's error contribution is multiplied by the
/// map value (the scan_candidates_weighted scoring), so threads concentrate
/// on high-weight regions. Without weights the arithmetic is unchanged. With
/// `min_chord = Some(d)` candidates closer than d pixels are skipped; on a
/// dead end (every chord from the current nail is masked out) the search
/// takes the best masked-out pull once instead of stalling.
///
/// The line cache is rasterized in parallel (result-preserving: each line is
/// deterministic, chunks are reassembled in source order).
///
/// An incremental improvement cache was evaluated here and rejected — see
/// docs/optimization.md (stage 7): with canvas-crossing chords the per-line
/// invalidation fan-out rivals the full rescan cost, so the cache measured
/// 0.4-0.6x of the plain scan throughput.
#[pyfunction(signature = (nails, orig, strength, i_limit=None, random_nails=None, white=true, weights=None, min_chord=None))]
fn create_art(
    py: Python<'_>,
    nails: Vec<(i64, i64)>,
    orig: &Image,
    strength: f64,
    i_limit: Option<u64>,
    random_nails: Option<u64>,
    white: bool,
    weights: Option<&Image>,
    min_chord: Option<f64>,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 {
        return Err(PyValueError::new_err("create_art needs a grayscale target"));
    }
    let weight_map: Vec<f64> = match weights {
        None => Vec::new(),
        Some(w) => {
            if w.ch != 1 || w.w != orig.w || w.h != orig.h {
                return Err(PyValueError::new_err(
                    "weights must be grayscale with the same shape as orig",
                ));
            }
            w.data.clone()
        }
    };
    let (w, h) = (orig.w, orig.h);
    let n = nails.len();

    let order: Vec<usize> = match random_nails {
        None => (0..n).collect(),
        Some(k) => seeded_subset(n, k as usize, 42),
    };

    // parallel rasterization across sources
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
            let nails_ref = &nails;
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
                log_debug(py, "min-chord dead end: no candidate clears the threshold, taking the best masked-out pull");
            }
            best_target = fb_target;
            best_range = fb_range;
        }

        pull_order.push(best_target);
        for k in best_range.0..best_range.1 {
            let px = sl.flat_idx[k] as usize;
            pic[px] = (pic[px] + strength * sl.val[k]).clamp(0.0, 1.0);
        }
        current = best_target as usize;
    }

    Ok((pull_order, Image { data: pic, w, h, ch: 1 }))
}

// ---------------------------------------------------------------------------
// Experimental lookahead searches: beam width, receding horizon (MPC)
// ---------------------------------------------------------------------------

/// One beam hypothesis: a partial pull sequence with its own working canvas.
struct BeamState {
    pic: Vec<f64>,
    current: usize,
    score: f64,
    order: Vec<u64>,
}

/// Scan every candidate pull from `state`. Read-only against the canvas.
fn scan_candidates(
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

fn apply_line(sl: &SourceLines, pic: &mut [f64], s0: usize, s1: usize, strength: f64) {
    for k in s0..s1 {
        let px = sl.flat_idx[k] as usize;
        pic[px] = (pic[px] + strength * sl.val[k]).clamp(0.0, 1.0);
    }
}

/// Offer a candidate to a descending top-W list. Later candidates win ties,
/// which reproduces the greedy `>=` tie-break when W == 1.
fn offer_top_w(
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

fn fork_states(
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

fn best_base_score(states: &[BeamState]) -> f64 {
    states
        .iter()
        .map(|s| s.score)
        .fold(f64::NEG_INFINITY, f64::max)
}

/// Shared parallel line-cache builder (the same rasterizer create_art uses).
fn build_cache(nails: &[(i64, i64)], w: usize) -> Vec<SourceLines> {
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
#[pyfunction(signature = (nails, orig, strength, i_limit=None, random_nails=None, white=true, beam=1))]
fn beam_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    strength: f64,
    i_limit: Option<u64>,
    random_nails: Option<u64>,
    white: bool,
    beam: u16,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 {
        return Err(PyValueError::new_err("beam_search needs a grayscale target"));
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
#[pyfunction(signature = (nails, orig, strength, i_limit=None, horizon=100, beam=8, random_nails=None, white=true))]
fn horizon_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    strength: f64,
    i_limit: Option<u64>,
    horizon: u32,
    beam: u16,
    random_nails: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 {
        return Err(PyValueError::new_err("horizon_search needs a grayscale target"));
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

fn scaled_nails(nails: &[(i64, i64)], x_ratio: f64, y_ratio: f64) -> Vec<(i64, i64)> {
    nails
        .iter()
        .map(|&(r, c)| ((y_ratio * r as f64) as i64, (x_ratio * c as f64) as i64))
        .collect()
}

/// Render a B/W pull order at the given resolution (port of
/// canvas.pull_order_to_array_bw; nail scaling included).
#[pyfunction]
fn render_bw(
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

/// Render interleaved RGB pull orders (port of canvas.pull_order_to_array_rgb).
#[pyfunction]
fn render_rgb(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strength: f64,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
) -> Image {
    let colors: [[f64; 3]; 3] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
    let nails = scaled_nails(&nails, out_w as f64 / in_w as f64, out_h as f64 / in_h as f64);
    let mut canvas = vec![if white { 1.0 } else { 0.0 }; out_w * out_h * 3];
    let pulls = orders.first().map(|o| o.len().saturating_sub(1)).unwrap_or(0);
    for step in 0..pulls {
        for (color_idx, order) in orders.iter().enumerate() {
            let (a, b) = (order[step] as usize, order[step + 1] as usize);
            let (rr, cc, val) = zingl_line(nails[a].0, nails[a].1, nails[b].0, nails[b].1);
            for k in 0..rr.len() {
                let px = (rr[k] as usize * out_w + cc[k] as usize).min(out_w * out_h - 1);
                for c in 0..3 {
                    canvas[px * 3 + c] += colors[color_idx][c] * val[k] * strength;
                }
            }
        }
    }
    for v in canvas.iter_mut() {
        *v = v.clamp(0.0, 1.0);
    }
    Image { data: canvas, w: out_w, h: out_h, ch: 3 }
}

// ---------------------------------------------------------------------------
// Metrics (ports of restring.metrics)
// ---------------------------------------------------------------------------

#[pyfunction]
fn mse(a: &Image, b: &Image) -> PyResult<f64> {
    same_shape(a, b)?;
    Ok(a.data.iter().zip(&b.data).map(|(x, y)| (x - y) * (x - y)).sum::<f64>() / a.data.len() as f64)
}

#[pyfunction]
fn corr(a: &Image, b: &Image) -> PyResult<f64> {
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

#[pyfunction]
fn ssim(a: &Image, b: &Image) -> PyResult<f64> {
    same_shape(a, b)?;
    if a.ch != 1 {
        return Err(PyValueError::new_err("ssim needs grayscale images"));
    }
    let (w, h) = (a.w, a.h);
    let win = 7usize;
    if w < win || h < win {
        return Err(PyValueError::new_err("image smaller than the SSIM window"));
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

fn same_shape(a: &Image, b: &Image) -> PyResult<()> {
    if a.w != b.w || a.h != b.h || a.ch != b.ch {
        return Err(PyValueError::new_err("metric needs same-shape images"));
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
fn scan_candidates_weighted(
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
#[pyfunction]
fn gaussian_weights(w: usize, h: usize, sigma: f64, peak: f64, bg: f64) -> Image {
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
#[pyfunction(signature = (nails, orig, weights, strength, i_limit=None, white=true))]
fn weighted_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    weights: &Image,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 || weights.ch != 1 {
        return Err(PyValueError::new_err("weighted_search needs grayscale images"));
    }
    if orig.w != weights.w || orig.h != weights.h {
        return Err(PyValueError::new_err("orig and weights must have the same shape"));
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
fn scan_candidates_asymmetric(
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
#[pyfunction(signature = (nails, orig, alpha, strength, i_limit=None, white=true))]
fn asymmetric_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    alpha: f64,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 {
        return Err(PyValueError::new_err("asymmetric_search needs a grayscale target"));
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
#[pyfunction(signature = (nails, orig, initial_pic, strength, i_limit=None, white=true))]
fn create_art_from(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    initial_pic: &Image,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 || initial_pic.ch != 1 {
        return Err(PyValueError::new_err("create_art_from needs grayscale images"));
    }
    if orig.w != initial_pic.w || orig.h != initial_pic.h {
        return Err(PyValueError::new_err("orig and initial_pic must have the same shape"));
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
#[pyfunction(signature = (nails, orig, pull_order, strength, sweeps=2))]
fn local_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    pull_order: Vec<u64>,
    strength: f64,
    sweeps: u32,
) -> PyResult<(Vec<u64>, Image)> {
    if orig.ch != 1 {
        return Err(PyValueError::new_err("local_search needs a grayscale target"));
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

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(line_aa, m)?)?;
    m.add_function(wrap_pyfunction!(circle_nails, m)?)?;
    m.add_function(wrap_pyfunction!(rect_nails, m)?)?;
    m.add_function(wrap_pyfunction!(create_art, m)?)?;
    m.add_function(wrap_pyfunction!(gaussian_weights, m)?)?;
    m.add_function(wrap_pyfunction!(beam_search, m)?)?;
    m.add_function(wrap_pyfunction!(horizon_search, m)?)?;
    m.add_function(wrap_pyfunction!(weighted_search, m)?)?;
    m.add_function(wrap_pyfunction!(asymmetric_search, m)?)?;
    m.add_function(wrap_pyfunction!(create_art_from, m)?)?;
    m.add_function(wrap_pyfunction!(local_search, m)?)?;
    m.add_function(wrap_pyfunction!(render_bw, m)?)?;
    m.add_function(wrap_pyfunction!(render_rgb, m)?)?;
    m.add_function(wrap_pyfunction!(mse, m)?)?;
    m.add_function(wrap_pyfunction!(corr, m)?)?;
    m.add_function(wrap_pyfunction!(ssim, m)?)?;
    m.add_class::<Image>()?;
    Ok(())
}
