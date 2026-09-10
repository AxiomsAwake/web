import { Cloud, Stage, Terrain } from "./simulation.js";

export const TERRAIN_COLORS = ["#e8f0fa", "#5693ce", "#7b4e23", "#4d8130", "#1d1d1b"];
export const BEAUFORT_COLORS = [
  "#ffffff", "#ccffff", "#99ffcc", "#99ff99", "#99ffcc", "#99ff00", "#ccff00",
  "#ffff00", "#ffcc00", "#ff9900", "#ff6600", "#ff3300", "#ff0000",
];

// The WPF original used a 1/13-cell temperature outline and quantized smog
// opacity. At responsive web sizes thousands of those outlines collapse into
// a checkerboard, so the same palette becomes a quiet, continuous field.
export const VISUAL_PROFILE = Object.freeze({
  temperatureFieldAlpha: 0.12,
  temperatureFieldSoloAlpha: 0.78,
  windMinAlpha: 0.42,
  windAlphaRange: 0.3,
  gridAlpha: 0.1,
  gridMinCellSize: 18,
});

export function pollutionOpacity(value) {
  const clamped = Math.max(0, Math.min(255, value));
  return Math.floor(clamped / 16) * 16 / 255;
}

const TEMPERATURE_STOPS = [
  [0, [47, 45, 54]],
  [0.16, [18, 11, 104]],
  [0.34, [0, 196, 236]],
  [0.52, [0, 190, 76]],
  [0.68, [184, 243, 0]],
  [0.8, [255, 221, 0]],
  [0.92, [255, 38, 0]],
  [1, [255, 246, 242]],
];

function interpolatePalette() {
  return Array.from({ length: 256 }, (_, value) => {
    const t = value / 255;
    let upper = 1;
    while (upper < TEMPERATURE_STOPS.length && TEMPERATURE_STOPS[upper][0] < t) upper += 1;
    const [startAt, start] = TEMPERATURE_STOPS[Math.max(0, upper - 1)];
    const [endAt, end] = TEMPERATURE_STOPS[Math.min(TEMPERATURE_STOPS.length - 1, upper)];
    const amount = endAt === startAt ? 0 : (t - startAt) / (endAt - startAt);
    const color = start.map((channel, i) => Math.round(channel + (end[i] - channel) * amount));
    return color;
  });
}

export class EarthRenderer {
  constructor(canvas, simulation, layers) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d", { alpha: false });
    this.simulation = simulation;
    this.layers = layers;
    this.temperatureRgb = interpolatePalette();
    this.temperatureLayer = document.createElement("canvas");
    this.temperatureLayer.width = simulation.width;
    this.temperatureLayer.height = simulation.height;
    this.temperatureLayerContext = this.temperatureLayer.getContext("2d", { alpha: false });
    this.temperatureImage = this.temperatureLayerContext.createImageData(simulation.width, simulation.height);
    this.selected = null;
    this.hovered = null;
    this.logicalWidth = 1;
    this.logicalHeight = 1;
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas);
    this.resize();
  }

  async loadTemperaturePalette(url) {
    try {
      const image = new Image();
      image.decoding = "async";
      image.src = url;
      await image.decode();
      const sampler = document.createElement("canvas");
      sampler.width = 256;
      sampler.height = 1;
      const context = sampler.getContext("2d", { willReadFrequently: true });
      context.drawImage(image, 0, 0, 256, 1);
      const pixels = context.getImageData(0, 0, 256, 1).data;
      this.temperatureRgb = Array.from({ length: 256 }, (_, index) => {
        const offset = index * 4;
        return [pixels[offset], pixels[offset + 1], pixels[offset + 2]];
      });
      this.draw();
    } catch {
      // The generated fallback follows the same cold-to-hot sequence.
    }
  }

  resize() {
    const bounds = this.canvas.getBoundingClientRect();
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    this.logicalWidth = Math.max(1, bounds.width);
    this.logicalHeight = Math.max(1, bounds.height);
    const width = Math.round(this.logicalWidth * ratio);
    const height = Math.round(this.logicalHeight * ratio);
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    this.draw();
  }

  setLayers(layers) {
    this.layers = layers;
    this.draw();
  }

  setSelected(cell) {
    this.selected = cell;
    this.draw();
  }

  setHovered(cell) {
    if (this.hovered?.index === cell?.index) return;
    this.hovered = cell;
    this.draw();
  }

  cellFromPointer(event) {
    const bounds = this.canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - bounds.left) / bounds.width * this.simulation.width);
    const y = Math.floor((event.clientY - bounds.top) / bounds.height * this.simulation.height);
    if (x < 0 || y < 0 || x >= this.simulation.width || y >= this.simulation.height) return null;
    return this.simulation.cellAt(x, y);
  }

  draw() {
    const simulation = this.simulation;
    const ctx = this.context;
    const width = this.logicalWidth;
    const height = this.logicalHeight;
    if (!ctx || width <= 1 || height <= 1) return;

    ctx.fillStyle = "#071116";
    ctx.fillRect(0, 0, width, height);
    const cellWidth = width / simulation.width;
    const cellHeight = height / simulation.height;
    const showClimate = simulation.stage === Stage.READY || simulation.stage === Stage.SIMULATION;

    for (let y = 0; y < simulation.height; y += 1) {
      for (let x = 0; x < simulation.width; x += 1) {
        const index = y * simulation.width + x;
        const left = x * cellWidth;
        const top = y * cellHeight;

        if (this.layers.terrain) {
          ctx.fillStyle = TERRAIN_COLORS[simulation.terrain[index]];
          ctx.fillRect(left, top, Math.ceil(cellWidth), Math.ceil(cellHeight));
        }

        if (this.layers.elevation && simulation.stage !== Stage.EMPTY) {
          const elevation = simulation.elevation[index];
          if (elevation >= 0) {
            ctx.fillStyle = `rgba(255,255,255,${Math.min(0.42, elevation / 8000)})`;
          } else {
            ctx.fillStyle = `rgba(0,17,34,${Math.min(0.38, Math.abs(elevation) / 9000)})`;
          }
          ctx.fillRect(left, top, Math.ceil(cellWidth), Math.ceil(cellHeight));
        }
      }
    }

    if (showClimate && this.layers.temperature) this.#drawTemperatureField(width, height);

    if (showClimate) {
      for (let y = 0; y < simulation.height; y += 1) {
        for (let x = 0; x < simulation.width; x += 1) {
          const index = y * simulation.width + x;
          const left = x * cellWidth;
          const top = y * cellHeight;
          if (this.layers.wind) this.#drawWind(index, left, top, cellWidth, cellHeight);
          if (this.layers.clouds) this.#drawCloud(index, left, top, cellWidth, cellHeight);

          // Smog was the final cell layer in the submitted renderer. Drawing it
          // last makes pollution read as atmosphere and naturally subdues every
          // climate glyph beneath a polluted cell.
          if (this.layers.pollution && simulation.pollution[index] > 32) {
            ctx.fillStyle = `rgba(176,170,139,${pollutionOpacity(simulation.pollution[index])})`;
            ctx.fillRect(left, top, Math.ceil(cellWidth), Math.ceil(cellHeight));
          }
        }
      }
    }

    if (Math.min(cellWidth, cellHeight) >= VISUAL_PROFILE.gridMinCellSize) {
      ctx.beginPath();
      ctx.strokeStyle = `rgba(6,17,22,${VISUAL_PROFILE.gridAlpha})`;
      ctx.lineWidth = 0.6;
      for (let x = 1; x < simulation.width; x += 1) {
        ctx.moveTo(x * cellWidth, 0);
        ctx.lineTo(x * cellWidth, height);
      }
      for (let y = 1; y < simulation.height; y += 1) {
        ctx.moveTo(0, y * cellHeight);
        ctx.lineTo(width, y * cellHeight);
      }
      ctx.stroke();
    }

    this.#drawFocus(this.hovered, "rgba(255,255,255,.62)", 1);
    this.#drawFocus(this.selected, "#71e6c6", 2);
  }

  #drawTemperatureField(width, height) {
    const pixels = this.temperatureImage.data;
    for (let index = 0; index < this.simulation.size; index += 1) {
      const color = this.temperatureRgb[this.simulation.temperature[index]];
      const offset = index * 4;
      pixels[offset] = color[0];
      pixels[offset + 1] = color[1];
      pixels[offset + 2] = color[2];
      pixels[offset + 3] = 255;
    }
    this.temperatureLayerContext.putImageData(this.temperatureImage, 0, 0);

    const ctx = this.context;
    ctx.save();
    ctx.globalAlpha = this.layers.terrain
      ? VISUAL_PROFILE.temperatureFieldAlpha
      : VISUAL_PROFILE.temperatureFieldSoloAlpha;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(this.temperatureLayer, 0, 0, width, height);
    ctx.restore();
  }

  #drawCloud(index, left, top, width, height) {
    const state = this.simulation.clouds[index];
    if (state === Cloud.CLEAR) return;
    const ctx = this.context;
    const radius = Math.max(1.6, Math.min(width, height) * 0.19);
    const cx = left + width / 2;
    const cy = top + height / 2 - (state === Cloud.RAINING ? radius * 0.12 : 0);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = state === Cloud.RAINING ? "#1b3852" : "rgba(255,255,255,.9)";
    ctx.strokeStyle = state === Cloud.RAINING ? "#143147" : "#4c4c4c";
    ctx.lineWidth = Math.max(0.8, radius * 0.18);
    ctx.fill();
    ctx.stroke();

    if (state === Cloud.RAINING && width > 12) {
      ctx.strokeStyle = "rgba(124,207,255,.58)";
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      for (const offset of [-0.55, 0, 0.55]) {
        ctx.moveTo(cx + radius * offset, cy + radius * 1.1);
        ctx.lineTo(cx + radius * offset - 0.7, cy + radius * 1.55);
      }
      ctx.stroke();
    }
  }

  #drawWind(index, left, top, width, height) {
    const simulation = this.simulation;
    const speed = simulation.windSpeed(index);
    if (speed < CALM_DISPLAY_THRESHOLD) return;
    const ctx = this.context;
    const force = simulation.beaufort(index);
    const angle = Math.atan2(-simulation.windY[index], simulation.windX[index]);
    const length = Math.min(width, height) * (0.2 + speed * 0.3);
    const cx = left + width / 2;
    const cy = top + height / 2;
    const tailX = cx - Math.cos(angle) * length * 0.45;
    const tailY = cy - Math.sin(angle) * length * 0.45;
    const tipX = cx + Math.cos(angle) * length * 0.55;
    const tipY = cy + Math.sin(angle) * length * 0.55;
    const head = Math.max(1.7, Math.min(width, height) * 0.13);

    ctx.save();
    ctx.globalAlpha = VISUAL_PROFILE.windMinAlpha + speed * VISUAL_PROFILE.windAlphaRange;
    ctx.strokeStyle = "rgba(19,31,35,.86)";
    ctx.fillStyle = BEAUFORT_COLORS[force];
    ctx.lineWidth = Math.max(0.8, Math.min(width, height) * 0.055);
    ctx.beginPath();
    ctx.moveTo(tailX, tailY);
    ctx.lineTo(tipX, tipY);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - Math.cos(angle - 0.55) * head, tipY - Math.sin(angle - 0.55) * head);
    ctx.lineTo(tipX - Math.cos(angle + 0.55) * head, tipY - Math.sin(angle + 0.55) * head);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  #drawFocus(cell, color, lineWidth) {
    if (!cell) return;
    const cellWidth = this.logicalWidth / this.simulation.width;
    const cellHeight = this.logicalHeight / this.simulation.height;
    this.context.strokeStyle = color;
    this.context.lineWidth = lineWidth;
    this.context.strokeRect(cell.x * cellWidth + lineWidth / 2, cell.y * cellHeight + lineWidth / 2, cellWidth - lineWidth, cellHeight - lineWidth);
  }
}

const CALM_DISPLAY_THRESHOLD = 0.3 / 35;
