const SERIES = [
  { key: "clear", label: "Clear", color: "#80b8ff" },
  { key: "cloudy", label: "Cloudy", color: "#d87970" },
  { key: "raining", label: "Rain", color: "#98c86c" },
  { key: "pollution", label: "Pollution", color: "#be8de5" },
  { key: "temperature", label: "Temperature", color: "#32d9ea" },
  { key: "wind", label: "Wind", color: "#f5b24e" },
];

function normalizedValues(history, key) {
  const values = history.map((entry) => entry[key]);
  const mean = values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(1, values.length);
  const deviation = Math.sqrt(variance);
  return deviation < 1e-9 ? values.map(() => 0) : values.map((value) => (value - mean) / deviation);
}

export class HistoryChart {
  constructor(canvas, simulation) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.simulation = simulation;
    this.logicalWidth = 1;
    this.logicalHeight = 1;
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas);
    this.resize();
  }

  resize() {
    const bounds = this.canvas.getBoundingClientRect();
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    this.logicalWidth = Math.max(1, bounds.width);
    this.logicalHeight = Math.max(1, bounds.height);
    this.canvas.width = Math.round(this.logicalWidth * ratio);
    this.canvas.height = Math.round(this.logicalHeight * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.draw();
  }

  draw() {
    const ctx = this.context;
    const history = this.simulation.history;
    const width = this.logicalWidth;
    const height = this.logicalHeight;
    ctx.clearRect(0, 0, width, height);

    const margin = { top: 12, right: 12, bottom: 28, left: 42 };
    const plotWidth = Math.max(1, width - margin.left - margin.right);
    const plotHeight = Math.max(1, height - margin.top - margin.bottom);
    ctx.fillStyle = "#09151b";
    ctx.fillRect(margin.left, margin.top, plotWidth, plotHeight);

    ctx.font = "12px ui-monospace, SFMono-Regular, Consolas, monospace";
    ctx.textBaseline = "middle";
    for (let value = -3; value <= 3; value += 1) {
      const y = margin.top + (3 - value) / 6 * plotHeight;
      ctx.beginPath();
      ctx.strokeStyle = value === 0 ? "rgba(182,213,220,.32)" : "rgba(182,213,220,.11)";
      ctx.lineWidth = value === 0 ? 1 : 0.6;
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + plotWidth, y);
      ctx.stroke();
      ctx.fillStyle = "#71858d";
      ctx.textAlign = "right";
      ctx.fillText(`${value}σ`, margin.left - 8, y);
    }

    if (history.length < 2) {
      ctx.fillStyle = "#71858d";
      ctx.textAlign = "center";
      ctx.font = "14px system-ui, sans-serif";
      ctx.fillText("Run the climate to reveal its trajectory", margin.left + plotWidth / 2, margin.top + plotHeight / 2);
      return;
    }

    for (const series of SERIES) {
      const values = normalizedValues(history, series.key);
      ctx.beginPath();
      ctx.strokeStyle = series.color;
      ctx.lineWidth = series.key === "pollution" || series.key === "temperature" ? 1.8 : 1.15;
      values.forEach((value, index) => {
        const x = margin.left + index / (values.length - 1) * plotWidth;
        const y = margin.top + (3 - Math.max(-3, Math.min(3, value))) / 6 * plotHeight;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    const first = history[0].generation;
    const last = history.at(-1).generation;
    ctx.fillStyle = "#71858d";
    ctx.textAlign = "left";
    ctx.fillText(String(first), margin.left, height - 12);
    ctx.textAlign = "right";
    ctx.fillText(String(last), margin.left + plotWidth, height - 12);
    ctx.textAlign = "center";
    ctx.fillText("generation", margin.left + plotWidth / 2, height - 12);
    this.canvas.setAttribute("aria-label", `Normalized climate history from generation ${first} to ${last}`);
  }
}

export { SERIES };
