import { HistoryChart } from "./chart.js";
import { EarthRenderer } from "./renderer.js";
import { CloudName, EarthSimulation, Stage, StageName, TerrainName } from "./simulation.js";

const simulation = new EarthSimulation(64, 36);
const canvas = document.querySelector("#earth-canvas");
const chartCanvas = document.querySelector("#history-chart");

const elements = {
  seed: document.querySelector("#seed-input"),
  pollution: document.querySelector("#pollution-input"),
  pollutionValue: document.querySelector("#pollution-value"),
  speed: document.querySelector("#speed-select"),
  generate: document.querySelector("#generate-button"),
  randomSeed: document.querySelector("#random-seed-button"),
  run: document.querySelector("#run-button"),
  step: document.querySelector("#step-button"),
  year: document.querySelector("#year-button"),
  reset: document.querySelector("#reset-button"),
  csv: document.querySelector("#csv-button"),
  stage: document.querySelector("#stage-label"),
  stageDot: document.querySelector("#stage-dot"),
  generation: document.querySelector("#generation-label"),
  build: document.querySelector("#build-label"),
  coordinate: document.querySelector("#coordinate-label"),
  stats: {
    clear: document.querySelector("#stat-clear"),
    cloudy: document.querySelector("#stat-cloudy"),
    raining: document.querySelector("#stat-raining"),
    pollution: document.querySelector("#stat-pollution"),
    temperature: document.querySelector("#stat-temperature"),
    wind: document.querySelector("#stat-wind"),
    pollutionRange: document.querySelector("#range-pollution"),
    temperatureRange: document.querySelector("#range-temperature"),
    windRange: document.querySelector("#range-wind"),
  },
  terrain: ["ice", "water", "ground", "forest", "city"].map((name) => document.querySelector(`#mix-${name}`)),
  inspectorEmpty: document.querySelector("#inspector-empty"),
  inspectorContent: document.querySelector("#inspector-content"),
  inspector: {
    coordinate: document.querySelector("#cell-coordinate"),
    terrain: document.querySelector("#cell-terrain"),
    elevation: document.querySelector("#cell-elevation"),
    temperature: document.querySelector("#cell-temperature"),
    pollution: document.querySelector("#cell-pollution"),
    clouds: document.querySelector("#cell-clouds"),
    wind: document.querySelector("#cell-wind"),
  },
};

const layerInputs = [...document.querySelectorAll("[data-layer]")];
const layers = Object.fromEntries(layerInputs.map((input) => [input.dataset.layer, input.checked]));
const renderer = new EarthRenderer(canvas, simulation, layers);
const chart = new HistoryChart(chartCanvas, simulation);
renderer.loadTemperaturePalette("./assets/heat-map-palette.jpg");

let building = false;
let running = false;
let runUntil = null;
let selectedCoordinates = null;
let lastFrame = performance.now();
let accumulator = 0;

function parseSeed() {
  const parsed = Number(elements.seed.value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 935527044;
}

function generateWorld() {
  running = false;
  runUntil = null;
  accumulator = 0;
  simulation.generate(parseSeed(), Number(elements.pollution.value));
  elements.seed.value = String(simulation.seed);
  building = true;
  selectedCoordinates = null;
  renderer.setSelected(null);
  renderAll();
}

function resetWorld() {
  running = false;
  building = false;
  runUntil = null;
  simulation.reset();
  selectedCoordinates = null;
  renderer.setSelected(null);
  renderAll();
}

function randomizeSeed() {
  const value = new Int32Array(1);
  crypto.getRandomValues(value);
  elements.seed.value = String(value[0]);
  generateWorld();
}

function toggleRun() {
  if (building || simulation.stage === Stage.EMPTY) return;
  running = !running;
  if (!running) runUntil = null;
  updateInterface();
}

function singleStep() {
  if (building || simulation.stage === Stage.EMPTY) return;
  running = false;
  runUntil = null;
  simulation.step();
  renderAll();
}

function runOneYear() {
  if (building || simulation.stage === Stage.EMPTY) return;
  runUntil = simulation.generation + 365;
  running = true;
  updateInterface();
}

function downloadCsv() {
  if (simulation.history.length === 0) return;
  const blob = new Blob([simulation.exportCsv(50)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `stats_randseed${simulation.seed}_poll${simulation.pollutionRamp}_gen${simulation.generation}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function format(value) {
  return Number(value).toFixed(4);
}

function percent(value) {
  return `${Math.round(value * 100)}%`;
}

function updateInterface() {
  const stats = simulation.stats;
  elements.stage.textContent = StageName[simulation.stage];
  elements.stageDot.classList.toggle("is-live", running);
  elements.stageDot.classList.toggle("is-building", building);
  elements.generation.textContent = String(simulation.generation);
  elements.build.textContent = String(simulation.buildIteration);
  elements.pollutionValue.textContent = elements.pollution.value;

  elements.stats.clear.textContent = format(stats.clear);
  elements.stats.cloudy.textContent = format(stats.cloudy);
  elements.stats.raining.textContent = format(stats.raining);
  elements.stats.pollution.textContent = format(stats.pollution);
  elements.stats.temperature.textContent = format(stats.temperature);
  elements.stats.wind.textContent = format(stats.wind);
  elements.stats.pollutionRange.textContent = `${format(stats.pollutionMin)}–${format(stats.pollutionMax)} · σ ${format(stats.pollutionDeviation)}`;
  elements.stats.temperatureRange.textContent = `${format(stats.temperatureMin)}–${format(stats.temperatureMax)} · σ ${format(stats.temperatureDeviation)}`;
  elements.stats.windRange.textContent = `${format(stats.windMin)}–${format(stats.windMax)} · σ ${format(stats.windDeviation)}`;
  stats.terrainCounts.forEach((count, index) => { elements.terrain[index].textContent = percent(count / simulation.size); });

  const unavailable = building || simulation.stage === Stage.EMPTY;
  elements.run.disabled = unavailable;
  elements.step.disabled = unavailable;
  elements.year.disabled = unavailable;
  elements.csv.disabled = simulation.generation < 50;
  elements.run.textContent = running ? "Pause" : (simulation.generation === 0 ? "Run climate" : "Resume");
  elements.run.setAttribute("aria-pressed", String(running));
  elements.speed.disabled = unavailable;

  if (selectedCoordinates) {
    const cell = simulation.cellAt(selectedCoordinates.x, selectedCoordinates.y);
    renderer.selected = cell;
    elements.inspectorEmpty.hidden = true;
    elements.inspectorContent.hidden = false;
    elements.inspector.coordinate.textContent = `${cell.x}, ${cell.y}`;
    elements.inspector.terrain.textContent = cell.terrainName;
    elements.inspector.elevation.textContent = `${cell.elevation.toLocaleString()} m`;
    elements.inspector.temperature.textContent = `${cell.temperature} / 255`;
    elements.inspector.pollution.textContent = `${cell.pollution.toFixed(1)} / 255`;
    elements.inspector.clouds.textContent = CloudName[cell.cloud];
    elements.inspector.wind.textContent = `${cell.windSpeed.toFixed(3)} · Beaufort ${cell.beaufort}`;
  } else {
    elements.inspectorEmpty.hidden = false;
    elements.inspectorContent.hidden = true;
  }
}

function renderAll() {
  renderer.draw();
  chart.draw();
  updateInterface();
}

function animate(now) {
  const elapsed = Math.min(250, now - lastFrame);
  lastFrame = now;
  let changed = false;

  if (building) {
    for (let iteration = 0; iteration < 3 && building; iteration += 1) {
      building = simulation.advanceBuild();
      changed = true;
      if (simulation.buildIteration > 500) {
        building = false;
        console.error("World generation exceeded its convergence budget");
      }
    }
  } else if (running) {
    const requestedSpeed = Number(elements.speed.value);
    if (requestedSpeed === 0) {
      for (let step = 0; step < 8; step += 1) simulation.step();
      changed = true;
    } else {
      accumulator += elapsed;
      const interval = 1000 / requestedSpeed;
      let steps = 0;
      while (accumulator >= interval && steps < 10) {
        simulation.step();
        accumulator -= interval;
        steps += 1;
        changed = true;
      }
    }

    if (runUntil !== null && simulation.generation >= runUntil) {
      running = false;
      runUntil = null;
    }
  }

  if (changed) renderAll();
  requestAnimationFrame(animate);
}

elements.generate.addEventListener("click", generateWorld);
elements.randomSeed.addEventListener("click", randomizeSeed);
elements.reset.addEventListener("click", resetWorld);
elements.run.addEventListener("click", toggleRun);
elements.step.addEventListener("click", singleStep);
elements.year.addEventListener("click", runOneYear);
elements.csv.addEventListener("click", downloadCsv);
elements.pollution.addEventListener("input", () => {
  simulation.setPollutionRamp(Number(elements.pollution.value));
  elements.pollutionValue.textContent = elements.pollution.value;
});

for (const input of layerInputs) {
  input.addEventListener("change", () => {
    layers[input.dataset.layer] = input.checked;
    renderer.setLayers(layers);
  });
}

canvas.addEventListener("pointermove", (event) => {
  const cell = renderer.cellFromPointer(event);
  renderer.setHovered(cell);
  elements.coordinate.textContent = cell ? `${cell.x}, ${cell.y} · ${TerrainName[cell.terrain]}` : "";
});
canvas.addEventListener("pointerleave", () => {
  renderer.setHovered(null);
  elements.coordinate.textContent = "";
});
canvas.addEventListener("click", (event) => {
  const cell = renderer.cellFromPointer(event);
  if (!cell) return;
  selectedCoordinates = { x: cell.x, y: cell.y };
  renderer.setSelected(cell);
  updateInterface();
});
canvas.addEventListener("keydown", (event) => {
  if (!event.key.startsWith("Arrow")) return;
  event.preventDefault();
  const current = selectedCoordinates || { x: Math.floor(simulation.width / 2), y: Math.floor(simulation.height / 2) };
  if (event.key === "ArrowLeft") current.x -= 1;
  if (event.key === "ArrowRight") current.x += 1;
  if (event.key === "ArrowUp") current.y -= 1;
  if (event.key === "ArrowDown") current.y += 1;
  selectedCoordinates = {
    x: (current.x + simulation.width) % simulation.width,
    y: (current.y + simulation.height) % simulation.height,
  };
  renderer.setSelected(simulation.cellAt(selectedCoordinates.x, selectedCoordinates.y));
  updateInterface();
});

document.addEventListener("keydown", (event) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  if (event.code === "Space") { event.preventDefault(); toggleRun(); }
  if (event.key === ".") singleStep();
});

generateWorld();
requestAnimationFrame(animate);
