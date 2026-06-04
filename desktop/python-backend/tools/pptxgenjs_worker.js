#!/usr/bin/env node
/**
 * PptxGenJS Worker Script
 * 
 * Reads JSON config from stdin, generates a PPTX file, outputs result as JSON to stdout.
 * 
 * Usage:
 *   echo '{"path":"out.pptx","slides":[...]}' | node pptxgenjs_worker.js
 * 
 * Config format:
 * {
 *   "path": "output.pptx",           // Required: output file path
 *   "layout": "LAYOUT_16x9",         // Optional: LAYOUT_16x9|LAYOUT_16x10|LAYOUT_4x3|LAYOUT_WIDE
 *   "title": "Presentation Title",   // Optional
 *   "author": "Author Name",         // Optional
 *   "slides": [...]                  // Required: array of slide definitions
 * }
 * 
 * Slide definition:
 * {
 *   "background": { "color": "1E2761" } | { "path": "https://..." },
 *   "transition": { "type": "fade", "duration": 1.0 },  // Optional: slide transition
 *   "elements": [...]  // Array of text, shape, image, chart, table elements
 * }
 * 
 * Element types:
 * - text: { "type": "text", "text": "Hello"|"[{text,options}]", ... }
 * - shape: { "type": "shape", "shape": "rect|oval|line|rounded_rect", ... }
 * - image: { "type": "image", "path": "file|url|base64", ... }
 * - chart: { "type": "chart", "chartType": "bar|line|pie|doughnut|scatter|radar", "data": [...], ... }
 * - table: { "type": "table", "rows": [[...]], ... }
 * 
 * Common properties (text/shape/image):
 *   x, y, w, h (inches), fill, line, shadow, rotate, transparency, hyperlink
 * 
 * Text properties:
 *   fontSize, fontFace, color, bold, italic, underline, align, valign,
 *   charSpacing, margin, bullet, breakLine, indentLevel, paraSpaceAfter
 */

const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// Read stdin
let inputData = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { inputData += chunk; });
process.stdin.on("end", async () => {
  try {
    const config = JSON.parse(inputData);
    const result = await generatePptx(config);
    process.stdout.write(JSON.stringify(result));
  } catch (err) {
    process.stdout.write(JSON.stringify({ error: err.message, success: false }));
    process.exit(1);
  }
});

async function generatePptx(config) {
  const pres = new pptxgen();
  
  // Layout
  const layoutMap = {
    "16x9": "LAYOUT_16x9", "16x10": "LAYOUT_16x10",
    "4x3": "LAYOUT_4x3", "wide": "LAYOUT_WIDE",
    "LAYOUT_16x9": "LAYOUT_16x9", "LAYOUT_16x10": "LAYOUT_16x10",
    "LAYOUT_4x3": "LAYOUT_4x3", "LAYOUT_WIDE": "LAYOUT_WIDE",
  };
  pres.layout = layoutMap[config.layout] || "LAYOUT_16x9";
  if (config.title) pres.title = config.title;
  if (config.author) pres.author = config.author;

  // Process slides
  const slides = config.slides || [];
  for (const slideDef of slides) {
    const slide = pres.addSlide();

    // Background
    if (slideDef.background) {
      slide.background = slideDef.background;
    }

    // Transition
    if (slideDef.transition) {
      const t = slideDef.transition;
      slide.transition = {
        type: t.type || "fade",
        duration: t.duration || 1.0,
      };
    }

    // Elements
    const elements = slideDef.elements || [];
    for (const el of elements) {
      try {
        addElement(pres, slide, el);
      } catch (elErr) {
        // Log element error but continue
        process.stderr.write(`Element error: ${elErr.message}\n`);
      }
    }
  }

  // Ensure output directory exists
  const outputPath = path.resolve(config.path);
  const outputDir = path.dirname(outputPath);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  // Write file (async)
  await pres.writeFile({ fileName: outputPath });
  
  const stats = fs.statSync(outputPath);
  return {
    path: outputPath,
    size: stats.size,
    slides: slides.length,
    success: true,
  };
}

function addElement(pres, slide, el) {
  const type = el.type || "text";
  
  switch (type) {
    case "text":
      addText(slide, el);
      break;
    case "shape":
      addShape(pres, slide, el);
      break;
    case "image":
      addImage(slide, el);
      break;
    case "chart":
      addChart(pres, slide, el);
      break;
    case "table":
      addTable(slide, el);
      break;
    default:
      throw new Error(`Unknown element type: ${type}`);
  }
}

function addText(slide, el) {
  const opts = extractTextOpts(el);
  
  // Support rich text arrays: el.text can be [{text, options}]
  if (Array.isArray(el.text)) {
    const textArr = el.text.map((item, idx) => {
      const itemOpts = extractTextOpts(item.options || item);
      if (idx < el.text.length - 1) {
        itemOpts.breakLine = true;
      }
      return { text: item.text || String(item), options: itemOpts };
    });
    slide.addText(textArr, opts);
  } else {
    slide.addText(el.text || "", opts);
  }
}

function extractTextOpts(el) {
  const opts = {};
  // Position/size
  if (el.x !== undefined) opts.x = el.x;
  if (el.y !== undefined) opts.y = el.y;
  if (el.w !== undefined) opts.w = el.w;
  if (el.h !== undefined) opts.h = el.h;
  // Font
  if (el.fontSize) opts.fontSize = el.fontSize;
  if (el.fontFace) opts.fontFace = el.fontFace;
  if (el.color) opts.color = el.color.replace("#", "");
  if (el.bold !== undefined) opts.bold = el.bold;
  if (el.italic !== undefined) opts.italic = el.italic;
  if (el.underline !== undefined) opts.underline = el.underline;
  // Alignment
  if (el.align) opts.align = el.align;
  if (el.valign) opts.valign = el.valign;
  // Spacing
  if (el.charSpacing !== undefined) opts.charSpacing = el.charSpacing;
  if (el.margin !== undefined) opts.margin = el.margin;
  if (el.paraSpaceAfter !== undefined) opts.paraSpaceAfter = el.paraSpaceAfter;
  // Bullet
  if (el.bullet !== undefined) opts.bullet = el.bullet;
  if (el.indentLevel !== undefined) opts.indentLevel = el.indentLevel;
  if (el.breakLine !== undefined) opts.breakLine = el.breakLine;
  // Background/fill
  if (el.fill) opts.fill = normalizeColor(el.fill);
  // Border/line
  if (el.line) opts.line = normalizeColor(el.line);
  // Shadow
  if (el.shadow) opts.shadow = normalizeShadow(el.shadow);
  // Hyperlink
  if (el.hyperlink) opts.hyperlink = el.hyperlink;
  // Rotation
  if (el.rotate !== undefined) opts.rotate = el.rotate;
  // Transparency
  if (el.transparency !== undefined) opts.transparency = el.transparency;
  // Shape-specific
  if (el.shape) opts.shape = el.shape;
  if (el.rectRadius !== undefined) opts.rectRadius = el.rectRadius;
  return opts;
}

function addShape(pres, slide, el) {
  const shapeMap = {
    "rect": pres.shapes.RECTANGLE,
    "rectangle": pres.shapes.RECTANGLE,
    "oval": pres.shapes.OVAL,
    "ellipse": pres.shapes.OVAL,
    "line": pres.shapes.LINE,
    "rounded_rect": pres.shapes.ROUNDED_RECTANGLE,
    "rounded_rect": pres.shapes.ROUNDED_RECTANGLE,
  };
  const shapeType = shapeMap[(el.shape || "rect").toLowerCase()] || pres.shapes.RECTANGLE;
  const opts = {};
  if (el.x !== undefined) opts.x = el.x;
  if (el.y !== undefined) opts.y = el.y;
  if (el.w !== undefined) opts.w = el.w;
  if (el.h !== undefined) opts.h = el.h;
  if (el.fill) opts.fill = normalizeColor(el.fill);
  if (el.line) opts.line = normalizeColor(el.line);
  if (el.shadow) opts.shadow = normalizeShadow(el.shadow);
  if (el.rectRadius !== undefined) opts.rectRadius = el.rectRadius;
  if (el.rotate !== undefined) opts.rotate = el.rotate;
  if (el.transparency !== undefined) opts.transparency = el.transparency;
  slide.addShape(shapeType, opts);
}

function addImage(slide, el) {
  const opts = {};
  // Image source: path, url, or base64 data
  if (el.data) {
    opts.data = el.data;
  } else if (el.path) {
    opts.path = el.path;
  }
  if (el.x !== undefined) opts.x = el.x;
  if (el.y !== undefined) opts.y = el.y;
  if (el.w !== undefined) opts.w = el.w;
  if (el.h !== undefined) opts.h = el.h;
  if (el.rotate !== undefined) opts.rotate = el.rotate;
  if (el.rounding !== undefined) opts.rounding = el.rounding;
  if (el.transparency !== undefined) opts.transparency = el.transparency;
  if (el.flipH !== undefined) opts.flipH = el.flipH;
  if (el.flipV !== undefined) opts.flipV = el.flipV;
  if (el.altText) opts.altText = el.altText;
  if (el.hyperlink) opts.hyperlink = el.hyperlink;
  if (el.sizing) opts.sizing = el.sizing;
  slide.addImage(opts);
}

function addChart(pres, slide, el) {
  const chartTypeMap = {
    "bar": pres.charts.BAR,
    "line": pres.charts.LINE,
    "pie": pres.charts.PIE,
    "doughnut": pres.charts.DOUGHNUT,
    "scatter": pres.charts.SCATTER,
    "radar": pres.charts.RADAR,
    "bubble": pres.charts.BUBBLE,
  };
  const chartType = chartTypeMap[(el.chartType || "bar").toLowerCase()] || pres.charts.BAR;
  
  // Data format: [{ name, labels, values }]
  const chartData = el.data || [];
  
  const opts = {};
  if (el.x !== undefined) opts.x = el.x;
  if (el.y !== undefined) opts.y = el.y;
  if (el.w !== undefined) opts.w = el.w;
  if (el.h !== undefined) opts.h = el.h;
  if (el.barDir) opts.barDir = el.barDir;
  if (el.showTitle !== undefined) opts.showTitle = el.showTitle;
  if (el.title) opts.title = el.title;
  if (el.showLegend !== undefined) opts.showLegend = el.showLegend;
  if (el.legendPos) opts.legendPos = el.legendPos;
  if (el.showPercent !== undefined) opts.showPercent = el.showPercent;
  if (el.showValue !== undefined) opts.showValue = el.showValue;
  if (el.chartColors) opts.chartColors = el.chartColors;
  if (el.lineSize !== undefined) opts.lineSize = el.lineSize;
  if (el.lineSmooth !== undefined) opts.lineSmooth = el.lineSmooth;
  if (el.dataLabelPosition) opts.dataLabelPosition = el.dataLabelPosition;
  if (el.dataLabelColor) opts.dataLabelColor = el.dataLabelColor;
  if (el.catAxisLabelColor) opts.catAxisLabelColor = el.catAxisLabelColor;
  if (el.valAxisLabelColor) opts.valAxisLabelColor = el.valAxisLabelColor;
  if (el.valGridLine) opts.valGridLine = el.valGridLine;
  if (el.catGridLine) opts.catGridLine = el.catGridLine;
  if (el.chartArea) opts.chartArea = el.chartArea;
  
  slide.addChart(chartType, chartData, opts);
}

function addTable(slide, el) {
  const opts = {};
  if (el.x !== undefined) opts.x = el.x;
  if (el.y !== undefined) opts.y = el.y;
  if (el.w !== undefined) opts.w = el.w;
  if (el.h !== undefined) opts.h = el.h;
  if (el.border) opts.border = el.border;
  if (el.fill) opts.fill = normalizeColor(el.fill);
  if (el.colW) opts.colW = el.colW;
  if (el.autoPage !== undefined) opts.autoPage = el.autoPage;
  
  slide.addTable(el.rows || [], opts);
}

function normalizeColor(obj) {
  if (typeof obj === "string") {
    return { color: obj.replace("#", "") };
  }
  if (obj && obj.color) {
    obj.color = obj.color.replace("#", "");
  }
  return obj;
}

function normalizeShadow(obj) {
  if (!obj) return obj;
  const shadow = { ...obj };
  if (shadow.color) shadow.color = shadow.color.replace("#", "");
  // Ensure offset is non-negative (negative corrupts file)
  if (shadow.offset !== undefined && shadow.offset < 0) shadow.offset = Math.abs(shadow.offset);
  return shadow;
}
