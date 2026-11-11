//! Browser binding for the ReString core: decode a photo, run the greedy
//! search, render PNG bytes. Serial and deterministic; the search's thread
//! cache falls back to a single thread on wasm automatically.

use wasm_bindgen::prelude::*;

use restring_core as core;

const GRID: usize = 300;
const MAX_PULLS: usize = 10_000;

fn to_js_error(message: String) -> JsError {
    JsError::new(&message)
}

/// Decoded, preprocessed photo: square-cropped and resampled to the 300 px
/// working grid, ready for the search.
#[wasm_bindgen]
pub struct WasmImage {
    inner: core::Image,
}

/// A finished search: pull order, nail layout and the export strength the
/// render uses.
#[wasm_bindgen]
pub struct WasmArt {
    order: Vec<u64>,
    nails: Vec<(i64, i64)>,
    pulls: usize,
    export_strength: f64,
}

#[wasm_bindgen]
impl WasmArt {
    /// Pull count of the wound sequence.
    #[wasm_bindgen(getter)]
    pub fn pulls(&self) -> usize {
        self.pulls
    }

    /// Nail count of the layout.
    #[wasm_bindgen(getter)]
    pub fn nails_count(&self) -> usize {
        self.nails.len()
    }
}

/// Decode PNG or JPEG bytes and preprocess to the working grid.
#[wasm_bindgen]
pub fn load_image(bytes: &[u8]) -> Result<WasmImage, JsError> {
    let decoded = image::load_from_memory(bytes)
        .map_err(|e| to_js_error(format!("cannot decode image: {e}")))?
        .to_rgb8();
    let (w, h) = decoded.dimensions();
    let data: Vec<f64> = decoded.into_raw().iter().map(|&b| b as f64 / 255.0).collect();
    let img = core::Image { data, w: w as usize, h: h as usize, ch: 3 };
    let square = img.largest_square();
    let resized = square.resize(GRID, GRID);
    Ok(WasmImage { inner: resized })
}

/// Run the greedy search. `layout` is "rect" or "circle". The working
/// strength is the measured 0.05 constant, like the CLI. `strength`
/// drives the render: None (or 0) fits the export strength from the
/// actual pull count, the fitted 104/L rule clamped to 0.03..0.3; a
/// value applies as given. The 10_000 budget is a cap, not a cost: at
/// working 0.05 saturation sits near 2900 pulls, and the search stops
/// on stagnation past it. `weight` (Some) concentrates threads toward
/// the center via the Gaussian map.
#[wasm_bindgen]
pub fn generate(
    image: &WasmImage,
    layout: &str,
    nail_step: usize,
    pulls: usize,
    strength: f64,
    weight: Option<f64>,
) -> Result<WasmArt, JsError> {
    let pulls = pulls.min(MAX_PULLS);
    let shape = (GRID, GRID);
    let nails = match layout {
        "rect" => core::rect_nails(GRID, GRID, nail_step),
        _ => core::circle_nails(GRID, GRID, nail_step, 1.0, 1.0),
    };
    let working_strength = -0.05;
    // strength 0 means auto: the fitted 104/L rule, same as the CLI default
    let export_strength = if strength.abs() > 1e-9 {
        -strength.abs().clamp(0.03, 0.3)
    } else {
        -(104.0 / pulls.max(1) as f64).clamp(0.03, 0.3)
    };
    let weights = weight.map(|peak| core::gaussian_weights(GRID, GRID, GRID as f64 / 3.0, peak, 0.5));
    let (order, _final) = core::create_art(
        nails.clone(),
        &image.inner.gray(0.9).map_err(to_js_error)?,
        working_strength,
        Some(pulls as u64),
        None,
        true,
        weights.as_ref(),
        None,
        false,
        None,
        None,
    )
    .map_err(to_js_error)?;
    Ok(WasmArt { pulls: order.len() - 1, nails, order, export_strength })
}

/// Render the art to PNG bytes at the given square size.
#[wasm_bindgen]
pub fn render_png(art: &WasmArt, size_px: usize) -> Result<Vec<u8>, JsError> {
    let rendered = core::render_bw(
        art.order.clone(),
        art.nails.clone(),
        art.export_strength,
        GRID,
        GRID,
        size_px,
        size_px,
        true,
    );
    let to_u8 = |v: f64| (v.clamp(0.0, 1.0) * 255.0) as u8;
    let buffer = image::ImageBuffer::<image::Luma<u8>, Vec<u8>>::from_fn(
        rendered.w as u32,
        rendered.h as u32,
        |x, y| image::Luma([to_u8(rendered.at(y as usize, x as usize, 0))]),
    );
    let mut bytes = std::io::Cursor::new(Vec::new());
    buffer
        .write_to(&mut bytes, image::ImageFormat::Png)
        .map_err(|e| to_js_error(format!("png encode failed: {e}")))?;
    Ok(bytes.into_inner())
}
