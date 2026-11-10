//! CPython binding for the ReString core (restring-core-algo). Thin shim:
//! every function delegates to the shared core crate, which also backs the
//! wasm binding. The Python-visible module stays `restring._core`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use restring_core as core;

// ---------------------------------------------------------------------------
// Image container
// ---------------------------------------------------------------------------

#[pyclass]
#[derive(Clone)]
struct Image {
    inner: core::Image,
}

#[pymethods]
impl Image {
    /// Load a PNG/JPEG file as an RGB float image in [0, 1].
    #[staticmethod]
    fn load(path: String) -> PyResult<Self> {
        core::Image::load(&path)
            .map(|img| Image { inner: img })
            .map_err(PyValueError::new_err)
    }

    /// Uniform canvas of the given value (1.0 = white, 0.0 = black).
    #[staticmethod]
    fn blank(w: usize, h: usize, ch: usize, value: f64) -> Self {
        Image { inner: core::Image::blank(w, h, ch, value) }
    }

    /// Build from nested lists: h x w (gray) or h x w x 3 (RGB).
    #[staticmethod]
    fn from_nested(rows: &Bound<'_, PyAny>) -> PyResult<Self> {
        if let Ok(flat) = rows.extract::<Vec<Vec<f64>>>() {
            core::Image::from_gray(&flat)
                .map(|img| Image { inner: img })
                .map_err(PyValueError::new_err)
        } else {
            let nested: Vec<Vec<Vec<f64>>> = rows.extract()?;
            core::Image::from_rgb(&nested)
                .map(|img| Image { inner: img })
                .map_err(PyValueError::new_err)
        }
    }

    fn box_blur(&self, radius: usize) -> Self {
        Image { inner: self.inner.box_blur(radius) }
    }

    fn shape(&self) -> (usize, usize, usize) {
        self.inner.shape()
    }

    fn pixel(&self, r: usize, c: usize, k: usize) -> PyResult<f64> {
        self.inner.pixel_checked(r, c, k).map_err(PyValueError::new_err)
    }

    fn tolist(&self, py: Python<'_>) -> PyObject {
        if self.inner.ch == 1 {
            self.inner.to_list().into_py(py)
        } else {
            self.inner.to_list_rgb().into_py(py)
        }
    }

    /// Central largest square crop (port of image_transformations.largest_square).
    fn largest_square(&self) -> Self {
        Image { inner: self.inner.largest_square() }
    }

    /// Anti-aliased box/bilinear resample (port of image_transformations.resize).
    fn resize(&self, out_w: usize, out_h: usize) -> Self {
        Image { inner: self.inner.resize(out_w, out_h) }
    }

    /// Grayscale (port of image_transformations.rgb2gray, times `scale`).
    fn gray(&self, scale: f64) -> PyResult<Self> {
        self.inner
            .gray(scale)
            .map(|img| Image { inner: img })
            .map_err(PyValueError::new_err)
    }

    /// Single channel of an RGB image as a gray image.
    fn channel(&self, k: usize) -> PyResult<Self> {
        self.inner
            .channel(k)
            .map(|img| Image { inner: img })
            .map_err(PyValueError::new_err)
    }

    /// Save as 8-bit PNG (L for gray, RGB otherwise); values clipped to [0, 1].
    fn save_png(&self, path: String) -> PyResult<()> {
        self.inner.save_png(&path).map_err(PyValueError::new_err)
    }
}

// ---------------------------------------------------------------------------
// Logging bridge: the core reports rollback and recovery notes as messages.
// ---------------------------------------------------------------------------

fn emit_messages(py: Python<'_>, messages: &[(String, String)]) {
    for (level, msg) in messages {
        let _ = py.import("logging").and_then(|log| {
            let logger = log.call_method1("getLogger", ("restring.core",))?;
            logger.call_method1(level.as_str(), (msg,))
        });
    }
}

/// Line rasterizer: identical to restring.canvas.line_aa (Zingl).
#[pyfunction]
fn line_aa(r0: i64, c0: i64, r1: i64, c1: i64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    core::line_aa(r0, c0, r1, c1)
}

/// Midpoint ellipse boundary nails, clockwise from 9 o'clock.
#[pyfunction]
fn circle_nails(w: usize, h: usize, nail_step: usize, r1_mult: f64, r2_mult: f64) -> Vec<(i64, i64)> {
    core::circle_nails(w, h, nail_step, r1_mult, r2_mult)
}

/// Rectangle border nails, clockwise from the top-left corner.
#[pyfunction]
fn rect_nails(w: usize, h: usize, nail_step: usize) -> Vec<(i64, i64)> {
    core::rect_nails(w, h, nail_step)
}

#[pyfunction(signature = (nails, orig, strength, i_limit=None, random_nails=None, white=true, weights=None, min_chord=None, rollback=false, seed=None))]
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
    rollback: bool,
    seed: Option<u64>,
) -> PyResult<(Vec<u64>, Image)> {
    let mut messages = Vec::new();
    let (order, final_img) = core::create_art(
        nails,
        &orig.inner,
        strength,
        i_limit,
        random_nails,
        white,
        weights.map(|w| &w.inner),
        min_chord,
        rollback,
        seed,
        Some(&mut messages),
    )
    .map_err(PyValueError::new_err)?;
    emit_messages(py, &messages);
    Ok((order, Image { inner: final_img }))
}

/// Gaussian center-focus weight map for importance-weighted search.
#[pyfunction]
fn gaussian_weights(w: usize, h: usize, sigma: f64, peak: f64, bg: f64) -> Image {
    Image { inner: core::gaussian_weights(w, h, sigma, peak, bg) }
}

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
    core::beam_search(nails, &orig.inner, strength, i_limit, random_nails, white, beam)
        .map(|(order, img)| (order, Image { inner: img }))
        .map_err(PyValueError::new_err)
}

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
    core::horizon_search(nails, &orig.inner, strength, i_limit, horizon, beam, random_nails, white)
        .map(|(order, img)| (order, Image { inner: img }))
        .map_err(PyValueError::new_err)
}

#[pyfunction(signature = (order, nails, strength, in_w, in_h, out_w, out_h, white, frames))]
fn animate_bw(
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
    core::animate_bw(order, nails, strength, in_w, in_h, out_w, out_h, white, frames)
        .into_iter()
        .map(|img| Image { inner: img })
        .collect()
}

#[pyfunction(signature = (orders, nails, strengths, in_w, in_h, out_w, out_h, white, frames))]
fn animate_rgb(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    frames: usize,
) -> PyResult<Vec<Image>> {
    core::animate_rgb(orders, nails, strengths, in_w, in_h, out_w, out_h, white, frames)
        .map(|frames| frames.into_iter().map(|img| Image { inner: img }).collect())
        .map_err(PyValueError::new_err)
}

#[pyfunction]
fn save_gif(path: String, images: Vec<PyRef<'_, Image>>, fps: u16) -> PyResult<usize> {
    let owned: Vec<core::Image> = images.iter().map(|img| img.inner.clone()).collect();
    core::save_gif(&path, &owned, fps).map_err(PyValueError::new_err)
}

/// Sobel gradient magnitude (grayscale; color collapses through luminance).
#[pyfunction]
fn gradient_magnitude(img: &Image) -> Image {
    Image { inner: core::gradient_magnitude(&img.inner) }
}

/// Anti-aliased thick segment: coverage = clamp(1 - (distance - half_width)).
#[pyfunction]
fn thick_line(r0: i64, c0: i64, r1: i64, c1: i64, half_width: f64) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    core::thick_line(r0, c0, r1, c1, half_width)
}

#[pyfunction(signature = (order, nails, strength, in_w, in_h, out_w, out_h, white, thread_px))]
fn render_bw_thick(
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
    Image { inner: core::render_bw_thick(order, nails, strength, in_w, in_h, out_w, out_h, white, thread_px) }
}

#[pyfunction(signature = (orders, nails, strengths, in_w, in_h, out_w, out_h, white, thread_px))]
fn render_rgb_thick(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
    thread_px: f64,
) -> PyResult<Image> {
    core::render_rgb_thick(orders, nails, strengths, in_w, in_h, out_w, out_h, white, thread_px)
        .map(|img| Image { inner: img })
        .map_err(PyValueError::new_err)
}

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
    Image { inner: core::render_bw(order, nails, strength, in_w, in_h, out_w, out_h, white) }
}

#[pyfunction]
fn render_rgb(
    orders: Vec<Vec<u64>>,
    nails: Vec<(i64, i64)>,
    strengths: Vec<f64>,
    in_w: usize,
    in_h: usize,
    out_w: usize,
    out_h: usize,
    white: bool,
) -> PyResult<Image> {
    core::render_rgb(orders, nails, strengths, in_w, in_h, out_w, out_h, white)
        .map(|img| Image { inner: img })
        .map_err(PyValueError::new_err)
}

#[pyfunction(signature = (orders, nails, colors, strengths, in_w, in_h, out_w, out_h, white, thread_px=None))]
fn render_palette(
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
) -> PyResult<Image> {
    core::render_palette(orders, nails, colors, strengths, in_w, in_h, out_w, out_h, white, thread_px)
        .map(|img| Image { inner: img })
        .map_err(PyValueError::new_err)
}

#[pyfunction]
fn mse(a: &Image, b: &Image) -> PyResult<f64> {
    core::mse(&a.inner, &b.inner).map_err(PyValueError::new_err)
}

#[pyfunction]
fn ssim_blur(a: &Image, b: &Image, radius: usize) -> PyResult<f64> {
    core::ssim_blur(&a.inner, &b.inner, radius).map_err(PyValueError::new_err)
}

#[pyfunction]
fn corr(a: &Image, b: &Image) -> PyResult<f64> {
    core::corr(&a.inner, &b.inner).map_err(PyValueError::new_err)
}

#[pyfunction]
fn ssim(a: &Image, b: &Image) -> PyResult<f64> {
    core::ssim(&a.inner, &b.inner).map_err(PyValueError::new_err)
}

#[pyfunction(signature = (nails, orig, weights, strength, i_limit=None, white=true))]
fn weighted_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    weights: &Image,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    core::weighted_search(nails, &orig.inner, &weights.inner, strength, i_limit, white)
        .map(|(order, img)| (order, Image { inner: img }))
        .map_err(PyValueError::new_err)
}

#[pyfunction(signature = (nails, orig, alpha, strength, i_limit=None, white=true))]
fn asymmetric_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    alpha: f64,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    core::asymmetric_search(nails, &orig.inner, alpha, strength, i_limit, white)
        .map(|(order, img)| (order, Image { inner: img }))
        .map_err(PyValueError::new_err)
}

#[pyfunction(signature = (nails, orig, initial_pic, strength, i_limit=None, white=true))]
fn create_art_from(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    initial_pic: &Image,
    strength: f64,
    i_limit: Option<u64>,
    white: bool,
) -> PyResult<(Vec<u64>, Image)> {
    core::create_art_from(nails, &orig.inner, &initial_pic.inner, strength, i_limit, white)
        .map(|(order, img)| (order, Image { inner: img }))
        .map_err(PyValueError::new_err)
}

#[pyfunction(signature = (nails, orig, pull_order, strength, sweeps=2))]
fn local_search(
    nails: Vec<(i64, i64)>,
    orig: &Image,
    pull_order: Vec<u64>,
    strength: f64,
    sweeps: u32,
) -> PyResult<(Vec<u64>, Image)> {
    core::local_search(nails, &orig.inner, pull_order, strength, sweeps)
        .map(|(order, img)| (order, Image { inner: img }))
        .map_err(PyValueError::new_err)
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
    m.add_function(wrap_pyfunction!(render_palette, m)?)?;
    m.add_function(wrap_pyfunction!(animate_bw, m)?)?;
    m.add_function(wrap_pyfunction!(animate_rgb, m)?)?;
    m.add_function(wrap_pyfunction!(save_gif, m)?)?;
    m.add_function(wrap_pyfunction!(thick_line, m)?)?;
    m.add_function(wrap_pyfunction!(gradient_magnitude, m)?)?;
    m.add_function(wrap_pyfunction!(ssim_blur, m)?)?;
    m.add_function(wrap_pyfunction!(render_bw_thick, m)?)?;
    m.add_function(wrap_pyfunction!(render_rgb_thick, m)?)?;
    m.add_function(wrap_pyfunction!(mse, m)?)?;
    m.add_function(wrap_pyfunction!(corr, m)?)?;
    m.add_function(wrap_pyfunction!(ssim, m)?)?;
    m.add_class::<Image>()?;
    Ok(())
}
