//! Rust core for ReString: the Zingl anti-aliased line rasterizer and the
//! greedy pull-order search, ported one-to-one from the Python implementation
//! (which itself ports skimage.draw.line_aa). Returns identical pull orders
//! up to floating-point summation order.

use pyo3::prelude::*;

/// Anti-aliased line — Zingl's Bresenham-based rasterizer (see restring.canvas).
#[pyfunction]
fn line_aa(r0: i64, c0: i64, r1: i64, c1: i64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
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

/// All lines leaving one source nail, CSR-style: segment k covers pixels
/// flat_idx[bounds[k]..bounds[k+1]] for the line to targets[k].
struct SourceLines {
    flat_idx: Vec<u32>,
    val: Vec<f64>,
    bounds: Vec<usize>,
    targets: Vec<u32>,
}

/// Greedy pull-order search — same semantics as restring.generator.create_art.
///
/// `orig_pic` and `pic` are row-major flattened canvases of `shape`; `pic`
/// doubles as the initial working canvas. `random_subset` carries candidate
/// indices pre-drawn on the Python side with numpy's default_rng(42), so both
/// backends always work with the same subset.
#[pyfunction]
fn create_art(
    nails: Vec<(i64, i64)>,
    orig_pic: Vec<f64>,
    shape: (usize, usize),
    mut pic: Vec<f64>,
    strength: f64,
    i_limit: Option<u64>,
    random_subset: Option<Vec<u64>>,
) -> (Vec<u64>, Vec<f64>) {
    let width = shape.1;
    let n = nails.len();
    let flat = |r: i64, c: i64| (r as usize * width + c as usize) as u32;

    // candidate iteration order mirrors the numpy scan: targets ascending,
    // or the given subset order; ties go to the last maximum (>=)
    let order: Vec<usize> = match &random_subset {
        None => (0..n).collect(),
        Some(s) => s.iter().map(|&x| x as usize).collect(),
    };

    // precompute all lines per source nail (CSR)
    let mut sources: Vec<SourceLines> = Vec::with_capacity(n);
    for i in 0..n {
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
            let (rr, cc, val) = line_aa(nails[i].0, nails[i].1, nails[j].0, nails[j].1);
            for k in 0..rr.len() {
                sl.flat_idx.push(flat(rr[k], cc[k]));
                sl.val.push(val[k]);
            }
            sl.bounds.push(sl.val.len());
            sl.targets.push(j as u32);
        }
        sources.push(sl);
    }

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

        let sl = &sources[current];
        let mut best_target: u64 = 0;
        let mut best_improvement = f64::NEG_INFINITY;
        let mut best_range = (0usize, 0usize);

        for &cand in &order {
            if cand == current || cand >= n {
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
                let cur = pic[px];
                let new = (cur + strength * sl.val[k]).clamp(0.0, 1.0);
                let o = orig_pic[px];
                improvement += (cur - o) * (cur - o) - (new - o) * (new - o);
            }
            if improvement >= best_improvement {
                best_improvement = improvement;
                best_target = cand as u64;
                best_range = (s0, s1);
            }
        }

        if best_improvement <= 0.0 {
            fails += 1;
            continue;
        }

        pull_order.push(best_target);
        for k in best_range.0..best_range.1 {
            let px = sl.flat_idx[k] as usize;
            pic[px] = (pic[px] + strength * sl.val[k]).clamp(0.0, 1.0);
        }
        current = best_target as usize;
    }

    (pull_order, pic)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(line_aa, m)?)?;
    m.add_function(wrap_pyfunction!(create_art, m)?)?;
    Ok(())
}
