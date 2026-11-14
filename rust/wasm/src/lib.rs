//! Browser binding for the ReString core: decode a photo, run the greedy
//! search in chunks with live previews, render PNG and GIF bytes, re-render
//! saved projects. Serial and deterministic; the search's thread cache falls
//! back to a single thread on wasm automatically.

use wasm_bindgen::prelude::*;

use restring_core as core;

const GRID: usize = 300;
const MAX_PULLS: usize = 10_000;
const AUTO_K: f64 = 104.0;
const AUTO_FLOOR: f64 = 0.03;
const AUTO_CEIL: f64 = 0.2;
const RGB_TRIPLE: [[f64; 3]; 3] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];

fn to_js_error(message: String) -> JsError {
    JsError::new(&message)
}

/// Decoded, preprocessed photo: square-cropped and resampled to the 300 px
/// working grid, ready for the search.
#[wasm_bindgen]
pub struct WasmImage {
    inner: core::Image,
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

/// A palette spec: a built-in name (rgb, cmy, cmyk) or a JSON array of
/// {"name", "rgb": [r, g, b]} entries, the palette-file convention.
fn palette_colors(spec: &str) -> Result<Vec<(String, [f64; 3])>, String> {
    let builtin: Option<Vec<(&str, [f64; 3])>> = match spec {
        "rgb" => Some(vec![("red", RGB_TRIPLE[0]), ("green", RGB_TRIPLE[1]), ("blue", RGB_TRIPLE[2])]),
        "cmy" => Some(vec![("cyan", [0.0, 1.0, 1.0]), ("magenta", [1.0, 0.0, 1.0]), ("yellow", [1.0, 1.0, 0.0])]),
        "cmyk" => Some(vec![("cyan", [0.0, 1.0, 1.0]), ("magenta", [1.0, 0.0, 1.0]), ("yellow", [1.0, 1.0, 0.0]), ("black", [1.0, 1.0, 1.0])]),
        _ => None,
    };
    if let Some(colors) = builtin {
        return Ok(colors.into_iter().map(|(n, c)| (n.to_string(), c)).collect());
    }
    let entries: Vec<serde_json::Value> =
        serde_json::from_str(spec).map_err(|e| format!("palette JSON: {e}"))?;
    let mut out = Vec::new();
    for entry in entries {
        let rgb = entry.get("rgb").and_then(|v| v.as_array())
            .ok_or_else(|| "palette entry needs an rgb array".to_string())?;
        if rgb.len() != 3 {
            return Err("palette rgb needs three values".to_string());
        }
        let mut color = [0.0f64; 3];
        for i in 0..3 {
            color[i] = rgb[i].as_f64()
                .ok_or_else(|| "palette rgb values must be numbers".to_string())?
                .clamp(0.0, 1.0);
        }
        let name = entry.get("name").and_then(|v| v.as_str()).unwrap_or("thread");
        out.push((name.to_string(), color));
    }
    if out.is_empty() {
        return Err("palette carries no thread colors".to_string());
    }
    if out.len() > 8 {
        return Err("palette exceeds the cap of 8 threads".to_string());
    }
    Ok(out)
}

/// One gray target per thread: the channel-weighted mean of the photo,
/// weights from the thread color (the generator.separate_targets contract).
fn separate_targets(img: &core::Image, colors: &[[f64; 3]]) -> Result<Vec<core::Image>, String> {
    if img.ch != 3 {
        return Err("color search needs an RGB photo".to_string());
    }
    let denoms: Vec<f64> = colors.iter().map(|c| c[0] + c[1] + c[2]).collect();
    if denoms.iter().any(|&d| d <= 0.0) {
        return Err("a thread color with all-zero rgb carries no darkness".to_string());
    }
    let mut maps = vec![vec![0.0; img.w * img.h]; colors.len()];
    for (idx, px) in img.data.chunks_exact(3).enumerate() {
        for (k, c) in colors.iter().enumerate() {
            maps[k][idx] = (c[0] * px[0] + c[1] * px[1] + c[2] * px[2]) / denoms[k];
        }
    }
    Ok(maps.into_iter()
        .map(|data| core::Image { data, w: img.w, h: img.h, ch: 1 })
        .collect())
}

fn encode_png(img: &core::Image) -> Result<Vec<u8>, JsError> {
    let to_u8 = |v: f64| (v.clamp(0.0, 1.0) * 255.0) as u8;
    let mut bytes = std::io::Cursor::new(Vec::new());
    if img.ch == 1 {
        let buffer = image::ImageBuffer::<image::Luma<u8>, Vec<u8>>::from_fn(
            img.w as u32, img.h as u32,
            |x, y| image::Luma([to_u8(img.at(y as usize, x as usize, 0))]),
        );
        buffer.write_to(&mut bytes, image::ImageFormat::Png)
            .map_err(|e| to_js_error(format!("png encode failed: {e}")))?;
    } else {
        let buffer = image::ImageBuffer::<image::Rgb<u8>, Vec<u8>>::from_fn(
            img.w as u32, img.h as u32,
            |x, y| image::Rgb([
                to_u8(img.at(y as usize, x as usize, 0)),
                to_u8(img.at(y as usize, x as usize, 1)),
                to_u8(img.at(y as usize, x as usize, 2)),
            ]),
        );
        buffer.write_to(&mut bytes, image::ImageFormat::Png)
            .map_err(|e| to_js_error(format!("png encode failed: {e}")))?;
    }
    Ok(bytes.into_inner())
}

/// A chunked search: build once, call step() to advance, render previews in
/// between. One core search per thread color, all sharing the line cache.
/// The playground drives this from a Web Worker so the page stays live.
#[wasm_bindgen]
pub struct WasmSearch {
    searches: Vec<core::Search>,
    nails: Vec<(i64, i64)>,
    colors: Vec<[f64; 3]>,
    names: Vec<String>,
    wb: bool,
    strength_override: f64,
    budget: usize,
    photo_gray: core::Image,
}

#[wasm_bindgen]
impl WasmSearch {
    /// `palette` is None for black-on-white (or white-on-black with wb),
    /// otherwise a built-in name or palette JSON text. `strength` 0 means
    /// auto: the fitted 104/L rule clamped to 0.03..0.2, like the CLI.
    #[wasm_bindgen(constructor)]
    pub fn new(
        image: &WasmImage,
        layout: &str,
        nail_step: usize,
        pulls: usize,
        strength: f64,
        weight: Option<f64>,
        palette: Option<String>,
        wb: bool,
    ) -> Result<WasmSearch, JsError> {
        let budget = pulls.clamp(1, MAX_PULLS);
        let nails = match layout {
            "rect" => core::rect_nails(GRID, GRID, nail_step),
            _ => core::circle_nails(GRID, GRID, nail_step, 1.0, 1.0),
        };
        let setup = core::SearchSetup::build(&nails, GRID, None, None, None);
        let working = if wb { 0.05 } else { -0.05 };
        let weights = weight.map(|peak| core::gaussian_weights(GRID, GRID, GRID as f64 / 3.0, peak, 0.5));

        let (targets, colors, names) = match palette {
            None => (vec![image.inner.gray(0.9).map_err(to_js_error)?], Vec::new(), Vec::new()),
            Some(spec) => {
                let resolved = palette_colors(&spec).map_err(to_js_error)?;
                let colors: Vec<[f64; 3]> = resolved.iter().map(|(_, c)| *c).collect();
                let names: Vec<String> = resolved.into_iter().map(|(n, _)| n).collect();
                let targets = separate_targets(&image.inner, &colors).map_err(to_js_error)?;
                (targets, colors, names)
            }
        };

        let mut searches = Vec::new();
        for target in &targets {
            // color runs ignore the weight map, like the CLI palette pipeline
            let w = if colors.is_empty() { weights.as_ref() } else { None };
            searches.push(
                core::Search::from_setup(&setup, target, working, Some(budget as u64), !wb, w, None)
                    .map_err(to_js_error)?,
            );
        }
        let photo_gray = image.inner.gray(1.0).map_err(to_js_error)?;
        Ok(WasmSearch {
            searches, nails, colors, names, wb,
            strength_override: strength, budget, photo_gray,
        })
    }

    /// Advance every thread by up to `pulls` new pulls. Returns the total
    /// pull count of the longest thread.
    pub fn step(&mut self, pulls: usize) -> usize {
        for search in &mut self.searches {
            search.step(pulls as u64);
        }
        self.pulls()
    }

    /// Pull count of the longest thread.
    #[wasm_bindgen(getter)]
    pub fn pulls(&self) -> usize {
        self.searches.iter().map(|s| s.pulls() as usize).max().unwrap_or(0)
    }

    /// Nail count of the layout.
    #[wasm_bindgen(getter)]
    pub fn nails_count(&self) -> usize {
        self.nails.len()
    }

    /// The requested pull budget (the cap, not the cost).
    #[wasm_bindgen(getter)]
    pub fn budget(&self) -> usize {
        self.budget
    }

    /// True when every thread hit its budget or stagnated.
    #[wasm_bindgen(getter)]
    pub fn finished(&self) -> bool {
        self.searches.iter().all(|s| s.finished())
    }

    fn thread_strength(&self, i: usize) -> f64 {
        let pulls = self.searches[i].pulls().max(1) as f64;
        let magnitude = if self.strength_override.abs() > 1e-9 {
            self.strength_override.abs().clamp(AUTO_FLOOR, AUTO_CEIL)
        } else {
            (AUTO_K / pulls).clamp(AUTO_FLOOR, AUTO_CEIL)
        };
        if self.wb { magnitude } else { -magnitude }
    }

    fn orders_padded(&self) -> Vec<Vec<u64>> {
        let max = self.searches.iter().map(|s| s.order().len()).max().unwrap_or(0);
        self.searches.iter().map(|s| {
            let mut order = s.order().to_vec();
            let last = *order.last().unwrap_or(&0);
            order.resize(max, last);
            order
        }).collect()
    }

    fn render_inner(&self, size_px: usize, strengths: &[f64]) -> core::Image {
        let white = !self.wb;
        if self.colors.is_empty() {
            core::render_bw(self.searches[0].order().to_vec(), self.nails.clone(),
                            strengths[0], GRID, GRID, size_px, size_px, white)
        } else {
            let colors = self.colors.iter().map(|c| (c[0], c[1], c[2])).collect();
            core::render_palette(self.orders_padded(), self.nails.clone(), colors,
                                 strengths.to_vec(), GRID, GRID, size_px, size_px, white, None)
                .unwrap_or_else(|_| core::Image::blank(size_px, size_px, 3, 1.0))
        }
    }

    /// Render the current state to PNG bytes at the given square size,
    /// export strength (auto-fitted from the current pull counts).
    pub fn render_png(&self, size_px: usize) -> Result<Vec<u8>, JsError> {
        let strengths: Vec<f64> = (0..self.searches.len()).map(|i| self.thread_strength(i)).collect();
        Ok(encode_png(&self.render_inner(size_px, &strengths))?)
    }

    /// MSE and SSIM of the current winding against the photo, both
    /// grayscale, at working strength. JSON: {"mse": ..., "ssim": ...}.
    pub fn quality_json(&self) -> Result<String, JsError> {
        let working = if self.wb { 0.05 } else { -0.05 };
        let strengths = vec![working; self.searches.len()];
        let render = self.render_inner(GRID, &strengths);
        let gray = if render.ch == 3 { render.gray(1.0).map_err(to_js_error)? } else { render };
        let mse = core::mse(&gray, &self.photo_gray).map_err(to_js_error)?;
        let ssim = core::ssim(&gray, &self.photo_gray).map_err(to_js_error)?;
        Ok(format!("{{\"mse\":{mse:.4},\"ssim\":{ssim:.4}}}"))
    }

    /// The winding as a project-shaped JSON payload: mode, wb, nails,
    /// orders and (for custom palettes) the thread colors. The page wraps
    /// this into a .restring file or feeds the winding assistant.
    pub fn orders_json(&self) -> String {
        let orders: Vec<String> = self.searches.iter().map(|s| {
            let items: Vec<String> = s.order().iter().map(|i| i.to_string()).collect();
            format!("[{}]", items.join(","))
        }).collect();
        let nails: Vec<String> = self.nails.iter().map(|(r, c)| format!("[{r},{c}]")).collect();
        let mode = if self.colors.is_empty() {
            "bw"
        } else if self.colors == RGB_TRIPLE {
            "rgb"
        } else {
            "palette"
        };
        let palette = if mode == "palette" {
            let entries: Vec<String> = self.names.iter().zip(&self.colors).map(|(name, c)| {
                format!("{{\"name\":{},\"rgb\":[{:.4},{:.4},{:.4}]}}",
                        serde_json::json!(name), c[0], c[1], c[2])
            }).collect();
            format!("[{}]", entries.join(","))
        } else {
            "null".to_string()
        };
        format!("{{\"mode\":\"{mode}\",\"wb\":{},\"nails\":[{}],\"orders\":[{}],\"palette\":{palette}}}",
                self.wb, nails.join(","), orders.join(","))
    }

    /// Animated GIF of the winding so far, export strength, 30 fps.
    pub fn animation_gif(&self, size_px: usize, frames: usize) -> Result<Vec<u8>, JsError> {
        let white = !self.wb;
        let strengths: Vec<f64> = (0..self.searches.len()).map(|i| self.thread_strength(i)).collect();
        let images = if self.colors.is_empty() {
            core::animate_bw(self.searches[0].order().to_vec(), self.nails.clone(),
                             strengths[0], GRID, GRID, size_px, size_px, white, frames)
        } else {
            core::animate_palette(self.orders_padded(), self.nails.clone(), self.colors.clone(),
                                  strengths, GRID, GRID, size_px, size_px, white, frames)
                .map_err(to_js_error)?
        };
        core::encode_gif(&images, 30).map_err(to_js_error)
    }
}

/// A finished one-shot search (the compatibility surface): pull order, nail
/// layout and the export strength the render uses.
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

/// Run the whole search in one call (black on white). The playground uses
/// WasmSearch in a worker instead; this stays for scripts and smoke tests.
#[wasm_bindgen]
pub fn generate(
    image: &WasmImage,
    layout: &str,
    nail_step: usize,
    pulls: usize,
    strength: f64,
    weight: Option<f64>,
) -> Result<WasmArt, JsError> {
    let mut search = WasmSearch::new(image, layout, nail_step, pulls, strength, weight, None, false)?;
    while !search.finished() {
        search.step(500);
    }
    let export_strength = search.thread_strength(0);
    Ok(WasmArt {
        pulls: search.pulls(),
        order: search.searches[0].order().to_vec(),
        nails: search.nails.clone(),
        export_strength,
    })
}

/// Render a finished one-shot art to PNG bytes at the given square size.
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
    encode_png(&rendered)
}

#[derive(serde::Deserialize)]
struct PaletteEntryIn {
    rgb: [f64; 3],
}

#[derive(serde::Deserialize)]
struct ConfigIn {
    #[serde(default)]
    wb: Option<bool>,
    #[serde(default)]
    grid: Option<serde_json::Value>,
}

#[derive(serde::Deserialize)]
struct ProjectIn {
    nails: Vec<[i64; 2]>,
    pull_orders: Vec<Vec<u64>>,
    #[serde(default)]
    mode: Option<String>,
    #[serde(default)]
    palette: Option<Vec<PaletteEntryIn>>,
    #[serde(default)]
    config: Option<ConfigIn>,
}

/// Re-render a .restring project JSON without a search: the browser loads a
/// saved project and renders it at any size and strength. `strength` 0 means
/// auto per thread, the same 104/L rule as the CLI.
#[wasm_bindgen]
pub fn render_project(project_json: &str, size_px: usize, strength: f64) -> Result<Vec<u8>, JsError> {
    let proj: ProjectIn = serde_json::from_str(project_json)
        .map_err(|e| to_js_error(format!("project JSON: {e}")))?;
    if proj.pull_orders.is_empty() || proj.nails.is_empty() {
        return Err(to_js_error("project needs nails and pull orders".to_string()));
    }
    let nails: Vec<(i64, i64)> = proj.nails.iter().map(|n| (n[0], n[1])).collect();
    let wb = proj.config.as_ref().and_then(|c| c.wb).unwrap_or(false);
    let (gh, gw) = match proj.config.as_ref().and_then(|c| c.grid.as_ref()) {
        Some(serde_json::Value::Array(a)) if a.len() == 2 => {
            (a[0].as_u64().unwrap_or(GRID as u64) as usize, a[1].as_u64().unwrap_or(GRID as u64) as usize)
        }
        Some(serde_json::Value::Number(n)) => {
            let g = n.as_u64().unwrap_or(GRID as u64) as usize;
            (g, g)
        }
        _ => (GRID, GRID),
    };
    let mode = proj.mode.as_deref().unwrap_or(if proj.pull_orders.len() == 1 { "bw" } else { "rgb" });
    let colors: Vec<[f64; 3]> = match mode {
        "bw" => Vec::new(),
        "rgb" => RGB_TRIPLE.to_vec(),
        _ => proj.palette.as_deref().unwrap_or(&[]).iter().map(|p| p.rgb).collect(),
    };
    if mode != "bw" && colors.len() != proj.pull_orders.len() {
        return Err(to_js_error("project palette needs one color per pull order".to_string()));
    }
    let strengths: Vec<f64> = proj.pull_orders.iter().map(|order| {
        let pulls = order.len().saturating_sub(1).max(1) as f64;
        let magnitude = if strength.abs() > 1e-9 {
            strength.abs().clamp(AUTO_FLOOR, AUTO_CEIL)
        } else {
            (AUTO_K / pulls).clamp(AUTO_FLOOR, AUTO_CEIL)
        };
        if wb { magnitude } else { -magnitude }
    }).collect();

    let rendered = if colors.is_empty() {
        core::render_bw(proj.pull_orders[0].clone(), nails, strengths[0],
                        gw, gh, size_px, size_px, !wb)
    } else {
        let colors = colors.iter().map(|c| (c[0], c[1], c[2])).collect();
        core::render_palette(proj.pull_orders.clone(), nails, colors, strengths,
                             gw, gh, size_px, size_px, !wb, None)
            .map_err(to_js_error)?
    };
    encode_png(&rendered)
}