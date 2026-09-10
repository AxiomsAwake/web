import { transportPollution } from "./pollution.js";
import { advectedCloud, NEIGHBOR_X, NEIGHBOR_Y } from "./weather.js";
import { DotNetRandom, normalizeSeed } from "./random.js";

export const Terrain = Object.freeze({
  ICE: 0,
  SEA: 1,
  LAND: 2,
  FOREST: 3,
  CITY: 4,
});

export const TerrainName = Object.freeze(["Ice", "Water", "Ground", "Forest", "City"]);

export const Cloud = Object.freeze({ CLEAR: 0, CLOUDY: 1, RAINING: 2 });
export const CloudName = Object.freeze(["Clear", "Cloudy", "Raining"]);

export const Stage = Object.freeze({
  EMPTY: "empty",
  TERRAIN: "terrain",
  ICE: "ice",
  FOREST: "forest",
  CITY: "city",
  READY: "ready",
  SIMULATION: "simulation",
});

export const StageName = Object.freeze({
  [Stage.EMPTY]: "Awaiting world",
  [Stage.TERRAIN]: "Continents settling",
  [Stage.ICE]: "Ice fields forming",
  [Stage.FOREST]: "Forests spreading",
  [Stage.CITY]: "Cities emerging",
  [Stage.READY]: "World ready",
  [Stage.SIMULATION]: "Climate evolving",
});

const INITIAL_TERRAIN_PERC = 0.63;
const INITIAL_ICE_PERC = 0.65;
const INITIAL_FOREST_PERC = 0.85;
const INITIAL_CITY_PERC = 0.9;
const AIR_QUALITY_DIFFUSE = 0.000029;
const CALM_THRESHOLD = 0.3 / 35;

const WIND_FROM = [
  [6, 2, 3], // top-left: SE, E, S
  [3, 7, 6], // top: S, SW, SE
  [7, 4, 3], // top-right: SW, W, S
  [2, 5, 6], // left: E, NE, SE
  [4, 7, 8], // right: W, SW, NW
  [5, 1, 2], // bottom-left: NE, N, E
  [1, 8, 5], // bottom: N, NW, NE
  [8, 1, 4], // bottom-right: NW, N, W
];

const clampByte = (value) => Math.max(0, Math.min(255, Math.round(Number.isFinite(value) ? value : 0)));
const square = (value) => value * value;

function meanAndDeviation(values) {
  if (values.length === 0) return { mean: 0, deviation: 0 };
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const deviation = Math.sqrt(values.reduce((sum, value) => sum + square(value - mean), 0) / values.length);
  return { mean, deviation };
}

export class EarthSimulation {
  constructor(width = 64, height = 36) {
    this.width = width;
    this.height = height;
    this.size = width * height;
    this.neighbors = this.#makeNeighborTable();

    this.terrain = new Uint8Array(this.size);
    this.heightNoise = new Float32Array(this.size);
    this.elevation = new Int16Array(this.size);
    this.temperature = new Uint8Array(this.size);
    this.pollution = new Float64Array(this.size);
    this.clouds = new Uint8Array(this.size);
    this.windX = new Float32Array(this.size);
    this.windY = new Float32Array(this.size);

    this.pollutionOutgoing = new Float64Array(this.size * 8);
    this.nextTerrain = new Uint8Array(this.size);
    this.nextTemperature = new Uint8Array(this.size);
    this.nextPollution = new Float64Array(this.size);
    this.nextClouds = new Uint8Array(this.size);
    this.nextWindX = new Float32Array(this.size);
    this.nextWindY = new Float32Array(this.size);

    this.reset();
  }

  reset() {
    this.terrain.fill(Terrain.SEA);
    this.heightNoise.fill(0);
    this.elevation.fill(-1000);
    this.temperature.fill(0);
    this.pollution.fill(0);
    this.clouds.fill(Cloud.CLEAR);
    this.windX.fill(0);
    this.windY.fill(0);
    this.stage = Stage.EMPTY;
    this.seed = 0;
    this.rng = new DotNetRandom(0);
    this.pollutionRamp = 0;
    this.emissionRise = 0;
    this.generation = 0;
    this.buildIteration = 0;
    this.phaseIteration = 0;
    this.buildOutcomes = [];
    this.history = [];
    this.stats = this.computeStatistics();
  }

  generate(seed, pollutionRamp = 0) {
    this.reset();
    this.seed = normalizeSeed(seed);
    this.pollutionRamp = Math.max(0, Math.min(25, Math.round(pollutionRamp)));
    this.rng = new DotNetRandom(this.seed);

    for (let x = 0; x < this.width; x += 1) {
      for (let y = 0; y < this.height; y += 1) {
        const index = y * this.width + x;
        this.terrain[index] = this.rng.nextDouble() > INITIAL_TERRAIN_PERC ? Terrain.LAND : Terrain.SEA;

        if (this.rng.nextDouble() > 0.99) {
          this.clouds[index] = this.rng.nextDouble() > 0.95 ? Cloud.RAINING : Cloud.CLOUDY;
        }

        this.temperature[index] = this.rng.next(256);
        let windX = 0;
        let windY = 0;
        if (this.rng.nextDouble() > 0.5) windX = (this.rng.nextDouble() - 0.5) * 2;
        if (this.rng.nextDouble() > 0.5) windY = (this.rng.nextDouble() - 0.5) * 2;
        this.#writeWind(this.windX, this.windY, index, Math.sign(windX) * square(windX), Math.sign(windY) * square(windY));
      }
    }

    this.stage = Stage.TERRAIN;
    this.stats = this.computeStatistics();
  }

  setPollutionRamp(value) {
    this.pollutionRamp = Math.max(0, Math.min(25, Math.round(value)));
  }

  advanceBuild(reverse = false) {
    if (![Stage.TERRAIN, Stage.ICE, Stage.FOREST, Stage.CITY].includes(this.stage)) return false;

    let changed = false;
    let periodTwo = this.phaseIteration > 0;
    for (let xi = 0; xi < this.width; xi += 1) {
      const x = reverse ? this.width - 1 - xi : xi;
      for (let y = 0; y < this.height; y += 1) {
        const index = y * this.width + x;
        const counts = this.#terrainCounts(index, true);
        const current = this.terrain[index];
        let next = current;

        if (this.stage === Stage.TERRAIN) {
          if (counts[Terrain.SEA] > 5) next = Terrain.SEA;
          else if (counts[Terrain.LAND] > 4) next = Terrain.LAND;
        } else if (this.stage === Stage.ICE) {
          if (counts[Terrain.ICE] > 3 && counts[Terrain.LAND] < 2) next = Terrain.ICE;
          else if (current === Terrain.ICE && counts[Terrain.SEA] > 4 && counts[Terrain.ICE] < 3) next = Terrain.SEA;
        } else if (this.stage === Stage.FOREST) {
          if (current === Terrain.LAND && counts[Terrain.SEA] < 3 && counts[Terrain.FOREST] > 3) next = Terrain.FOREST;
          else if (current === Terrain.FOREST && counts[Terrain.FOREST] > 6 && counts[Terrain.LAND] > 2) next = Terrain.LAND;
        } else if (this.stage === Stage.CITY) {
          if (current === Terrain.LAND && counts[Terrain.CITY] > 2 && counts[Terrain.CITY] < 6) next = Terrain.CITY;
          else if (current === Terrain.CITY && counts[Terrain.CITY] > 7) next = Terrain.LAND;
        }

        if (next !== this.nextTerrain[index]) periodTwo = false;
        this.nextTerrain[index] = next;
        if (next !== current) changed = true;
      }
    }
    [this.terrain, this.nextTerrain] = [this.nextTerrain, this.terrain];
    this.buildIteration += 1;
    this.phaseIteration += 1;

    // Synchronous rules can oscillate. World construction samples the latest
    // complete state on a detected 2-cycle or phase budget, never mutating the
    // transition rule to force convergence. Climate itself is never stopped.
    if (!changed || periodTwo || this.phaseIteration >= 100) {
      this.buildOutcomes.push({
        stage: this.stage,
        iterations: this.phaseIteration,
        reason: !changed ? "fixed-point" : periodTwo ? "period-2" : "budget",
      });
      this.phaseIteration = 0;
      if (this.stage === Stage.TERRAIN) {
        this.#generateElevation();
        this.stage = Stage.ICE;
        this.#seedIce();
      } else if (this.stage === Stage.ICE) {
        this.stage = Stage.FOREST;
        this.#seedForests();
      } else if (this.stage === Stage.FOREST) {
        this.stage = Stage.CITY;
        this.#seedCities();
      } else {
        this.stage = Stage.READY;
        this.#syncElevationToTerrain();
      }
    }

    this.stats = this.computeStatistics();
    return this.stage !== Stage.READY;
  }

  finishBuild(maxIterations = 400) {
    let iterations = 0;
    while (this.advanceBuild() && iterations < maxIterations) iterations += 1;
    if (this.stage !== Stage.READY) throw new Error("World generation did not converge");
    return iterations;
  }

  step(reverse = false) {
    if (this.stage === Stage.READY) this.stage = Stage.SIMULATION;
    if (this.stage !== Stage.SIMULATION) return this.stats;

    transportPollution(this.pollution, this.temperature, this.windX, this.windY,
      this.neighbors, this.pollutionOutgoing, this.nextPollution);
    const cloudSampleX = this.#cellRandom(0, 5);
    const cloudSampleY = this.#cellRandom(0, 6);

    for (let xi = 0; xi < this.width; xi += 1) {
      const x = reverse ? this.width - 1 - xi : xi;
      for (let y = 0; y < this.height; y += 1) {
        const index = y * this.width + x;
        const currentTemp = this.temperature[index];
        const currentPollution = Math.min(255, this.pollution[index]);
        // Retain momentum while neighboring vectors gradually align.
        const persistence = 0.95;
        let windX = this.windX[index] * persistence;
        let windY = this.windY[index] * persistence;
        let airQuality = this.nextPollution[index];
        let newTemperature = currentTemp;

        // This deliberately preserves the submitted 2012 feedback equation.
        newTemperature += (1 - newTemperature) * (currentPollution / 256);

        const windDiffusion = this.#cellRandom(index, 1) * 0.00005
          + currentTemp * 0.005
          - Math.sqrt(currentPollution / 256) * AIR_QUALITY_DIFFUSE;

        for (let slot = 0; slot < 8; slot += 1) {
          const neighbor = this.neighbors[index * 8 + slot];
          const direction = this.windDirection(neighbor);
          let windFromNeighbor = 0;

          if (direction === WIND_FROM[slot][0]) windFromNeighbor = 1;
          else if (direction === WIND_FROM[slot][1] || direction === WIND_FROM[slot][2]) windFromNeighbor = 0.7;

          const opposite = 7 - slot;
          if (direction === WIND_FROM[opposite][0]) windFromNeighbor = -1;
          else if (direction === WIND_FROM[opposite][1] || direction === WIND_FROM[opposite][2]) windFromNeighbor = -0.7;

          // Mix momentum as vectors. Outward-pointing neighbors must not be
          // subtracted: that cancels a perfectly uniform prevailing wind.
          let partX = this.windX[neighbor] * (1 - persistence) / 8;
          let partY = this.windY[neighbor] * (1 - persistence) / 8;
          const speed = this.windSpeed(neighbor) * windFromNeighbor;
          const temperatureWind = Math.abs(currentTemp / 255 - this.temperature[neighbor] / 255) / 9;
          const createdWind = (this.temperature[neighbor] - currentTemp) / 255 / 9
            + (this.elevation[neighbor] - this.elevation[index]) / 5000 * 0.0005;
          const distance = Math.hypot(NEIGHBOR_X[slot], NEIGHBOR_Y[slot]);
          partX -= NEIGHBOR_X[slot] / distance * createdWind / 9;
          partY -= NEIGHBOR_Y[slot] / distance * createdWind / 9;

          const speedWithDiffusion = speed + windDiffusion;
          newTemperature += (this.temperature[neighbor] - currentTemp + temperatureWind) * speedWithDiffusion;
          windX += partX;
          windY += partY;
        }

        let nextCloud = advectedCloud(index, this.clouds, this.windX, this.windY,
          this.neighbors, cloudSampleX, cloudSampleY);
        // Local heat/cleanup uses the old local sky; cloud advection carries
        // cloudy AND raining states intact. Phase changes are rare local events.
        if (this.clouds[index] === Cloud.CLEAR) newTemperature += 6;
        else if (this.clouds[index] === Cloud.CLOUDY) newTemperature -= 2;
        else { newTemperature -= 5; airQuality -= 1; }
        if (nextCloud === Cloud.CLEAR) {
          const highGroundLift = Math.max(0, this.elevation[index]) / 4000;
          const evaporating = this.terrain[index] === Terrain.SEA
            && square(currentTemp) > currentPollution
            && newTemperature > currentTemp
            && this.#cellRandom(index, 2) < 0.0001 + highGroundLift * 0.00002;
          if (evaporating) nextCloud = Cloud.CLOUDY;
        } else if (nextCloud === Cloud.CLOUDY) {
          if (this.#cellRandom(index, 3) < 0.001) nextCloud = Cloud.RAINING;
        } else {
          if (this.#cellRandom(index, 4) < 0.001) nextCloud = Cloud.CLEAR;
        }

        const terrain = this.terrain[index];
        if (terrain === Terrain.ICE) { newTemperature -= 3; airQuality -= 1; }
        else if (terrain === Terrain.SEA) { newTemperature -= 1; airQuality -= 1; }
        else if (terrain === Terrain.LAND) newTemperature += 5;
        else if (terrain === Terrain.FOREST) airQuality -= 4;
        else if (terrain === Terrain.CITY && this.generation > 15) airQuality += 10 + this.emissionRise;

        // The original assignment required elevation; the 2012 submission omitted it.
        // A restrained lapse-rate term restores that coupling without overwhelming the old rules.
        newTemperature -= Math.max(0, this.elevation[index]) / 4000 * 0.2;

        this.nextTemperature[index] = clampByte(newTemperature);
        // Keep excess quantity: a display ceiling must not delete emissions.
        this.nextPollution[index] = Math.max(0, airQuality);
        this.nextClouds[index] = nextCloud;
        this.#writeWind(this.nextWindX, this.nextWindY, index, windX, windY);
      }
    }

    // Publish the entire generation only after every cell has been evaluated.
    for (const [current, next] of [["temperature", "nextTemperature"], ["pollution", "nextPollution"], ["clouds", "nextClouds"], ["windX", "nextWindX"], ["windY", "nextWindY"]]) {
      [this[current], this[next]] = [this[next], this[current]];
    }

    this.emissionRise += this.pollutionRamp / 255;
    this.generation += 1;
    this.stats = this.computeStatistics();
    this.history.push({ generation: this.generation, ...this.stats });
    if (this.history.length > 1440) this.history.shift();
    return this.stats;
  }

  computeStatistics() {
    const cloudCounts = [0, 0, 0];
    const temperatures = [];
    const pollution = [];
    const winds = [];
    const terrainCounts = [0, 0, 0, 0, 0];

    for (let index = 0; index < this.size; index += 1) {
      cloudCounts[this.clouds[index]] += 1;
      terrainCounts[this.terrain[index]] += 1;
      temperatures.push(this.temperature[index] / 255);
      pollution.push(Math.min(255, this.pollution[index]) / 255);
      winds.push(this.windSpeed(index));
    }

    const temp = meanAndDeviation(temperatures);
    const poll = meanAndDeviation(pollution);
    const wind = meanAndDeviation(winds);
    return {
      clear: cloudCounts[Cloud.CLEAR] / this.size,
      cloudy: cloudCounts[Cloud.CLOUDY] / this.size,
      raining: cloudCounts[Cloud.RAINING] / this.size,
      pollution: poll.mean,
      pollutionDeviation: poll.deviation,
      pollutionMin: Math.min(...pollution),
      pollutionMax: Math.max(...pollution),
      temperature: temp.mean,
      temperatureDeviation: temp.deviation,
      temperatureMin: Math.min(...temperatures),
      temperatureMax: Math.max(...temperatures),
      wind: wind.mean,
      windDeviation: wind.deviation,
      windMin: Math.min(...winds),
      windMax: Math.max(...winds),
      terrainCounts,
    };
  }

  windSpeed(index) {
    return Math.min(1, Math.hypot(this.windX[index], this.windY[index]));
  }

  windDirection(index) {
    const x = Math.round(this.windX[index] * 100) / 100;
    const y = Math.round(this.windY[index] * 100) / 100;
    if (x === 0 && y === 0) return 0;
    if (x === 0) return y > 0 ? 1 : 3;
    if (x > 0) return y === 0 ? 2 : (y > 0 ? 5 : 6);
    return y === 0 ? 4 : (y > 0 ? 8 : 7);
  }

  beaufort(index) {
    const speed = this.windSpeed(index);
    const thresholds = [0.3, 1.6, 3.4, 5.5, 8, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7];
    for (let force = 0; force < thresholds.length; force += 1) {
      if (speed < thresholds[force] / 35) return force;
    }
    return 12;
  }

  cellAt(x, y) {
    const wrappedX = ((x % this.width) + this.width) % this.width;
    const wrappedY = ((y % this.height) + this.height) % this.height;
    const index = wrappedY * this.width + wrappedX;
    return {
      x: wrappedX,
      y: wrappedY,
      index,
      terrain: this.terrain[index],
      terrainName: TerrainName[this.terrain[index]],
      elevation: this.elevation[index],
      temperature: this.temperature[index],
      pollution: Math.min(255, this.pollution[index]),
      cloud: this.clouds[index],
      cloudName: CloudName[this.clouds[index]],
      windX: this.windX[index],
      windY: this.windY[index],
      windSpeed: this.windSpeed(index),
      beaufort: this.beaufort(index),
    };
  }

  exportCsv(fromGeneration = 50) {
    const rows = this.history.filter((entry) => entry.generation >= fromGeneration);
    const selected = rows.length > 0 ? rows : this.history;
    const header = [
      "simGen",
      "StatCloudsClear",
      "StatCloudsCloudy",
      "StatCloudsRaining",
      "StatPollutionAvgAirQuality",
      "StatPollutionAirQualityStdDev",
      "StatTemperatureAvgValue",
      "StatTemperatureValueStdDev",
      "StatWindAvgSpeed",
      "StatWindSpeedStdDev",
    ];
    const lines = selected.map((entry) => [
      entry.generation,
      entry.clear,
      entry.cloudy,
      entry.raining,
      entry.pollution,
      entry.pollutionDeviation,
      entry.temperature,
      entry.temperatureDeviation,
      entry.wind,
      entry.windDeviation,
    ].map((value) => typeof value === "number" ? Number(value.toFixed(6)) : value).join(","));
    return [header.join(","), ...lines].join("\n");
  }

  fingerprint() {
    let hash = 2166136261;
    const arrays = [this.terrain, this.temperature, this.pollution, this.clouds];
    for (const array of arrays) {
      for (const value of array) {
        hash ^= value;
        hash = Math.imul(hash, 16777619);
      }
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  #makeNeighborTable() {
    const table = new Int32Array(this.size * 8);
    const offsets = [[-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]];
    for (let y = 0; y < this.height; y += 1) {
      for (let x = 0; x < this.width; x += 1) {
        const index = y * this.width + x;
        offsets.forEach(([dx, dy], slot) => {
          const nx = (x + dx + this.width) % this.width;
          const ny = (y + dy + this.height) % this.height;
          table[index * 8 + slot] = ny * this.width + nx;
        });
      }
    }
    return table;
  }

  #terrainCounts(index, includeSelf) {
    const counts = [0, 0, 0, 0, 0];
    if (includeSelf) counts[this.terrain[index]] += 1;
    for (let slot = 0; slot < 8; slot += 1) counts[this.terrain[this.neighbors[index * 8 + slot]]] += 1;
    return counts;
  }

  #seedIce() {
    this.nextTerrain.set(this.terrain);
    for (let x = 0; x < this.width; x += 1) {
      for (let y = 0; y < this.height; y += 1) {
        const index = y * this.width + x;
        const counts = this.#terrainCounts(index, false);
        if (this.terrain[index] === Terrain.SEA
          && counts[Terrain.SEA] > 6
          && counts[Terrain.LAND] < 2
          && this.rng.nextDouble() > INITIAL_ICE_PERC) this.nextTerrain[index] = Terrain.ICE;
      }
    }
    [this.terrain, this.nextTerrain] = [this.nextTerrain, this.terrain];
    this.#syncElevationToTerrain();
  }

  #seedForests() {
    this.nextTerrain.set(this.terrain);
    for (let x = 0; x < this.width; x += 1) {
      for (let y = 0; y < this.height; y += 1) {
        const index = y * this.width + x;
        const counts = this.#terrainCounts(index, false);
        if (this.terrain[index] === Terrain.LAND
          && counts[Terrain.LAND] > 2
          && counts[Terrain.SEA] < 5
          && this.rng.nextDouble() > INITIAL_FOREST_PERC) this.nextTerrain[index] = Terrain.FOREST;
      }
    }
    [this.terrain, this.nextTerrain] = [this.nextTerrain, this.terrain];
  }

  #seedCities() {
    this.nextTerrain.set(this.terrain);
    for (let x = 0; x < this.width; x += 1) {
      for (let y = 0; y < this.height; y += 1) {
        const index = y * this.width + x;
        const counts = this.#terrainCounts(index, false);
        if (this.terrain[index] === Terrain.LAND
          && counts[Terrain.LAND] + counts[Terrain.FOREST] - counts[Terrain.SEA] > 3
          && this.rng.nextDouble() > INITIAL_CITY_PERC) this.nextTerrain[index] = Terrain.CITY;
      }
    }
    [this.terrain, this.nextTerrain] = [this.nextTerrain, this.terrain];
  }

  #generateElevation() {
    const elevationRng = new DotNetRandom(this.seed ^ 0x45d9f3b);
    let noise = new Float32Array(this.size);
    let scratch = new Float32Array(this.size);
    for (let index = 0; index < this.size; index += 1) noise[index] = elevationRng.nextDouble();

    for (let pass = 0; pass < 5; pass += 1) {
      for (let index = 0; index < this.size; index += 1) {
        let total = noise[index] * 4;
        for (let slot = 0; slot < 8; slot += 1) total += noise[this.neighbors[index * 8 + slot]];
        scratch[index] = total / 12;
      }
      [noise, scratch] = [scratch, noise];
    }

    let min = Infinity;
    let max = -Infinity;
    for (const value of noise) { min = Math.min(min, value); max = Math.max(max, value); }
    const span = max - min || 1;
    for (let index = 0; index < this.size; index += 1) this.heightNoise[index] = (noise[index] - min) / span;
    this.#syncElevationToTerrain();
  }

  #syncElevationToTerrain() {
    for (let index = 0; index < this.size; index += 1) {
      const noise = this.heightNoise[index];
      const terrain = this.terrain[index];
      if (terrain === Terrain.SEA) this.elevation[index] = Math.round(-400 - (1 - noise) * 3600);
      else if (terrain === Terrain.ICE) this.elevation[index] = Math.round(20 + noise * 180);
      else this.elevation[index] = Math.round(50 + Math.pow(noise, 1.6) * 3200);
    }
  }

  // Counter-based noise: fixed seed, cell, generation and event identify each
  // draw. A remote cell's branches cannot consume another cell's randomness.
  #cellRandom(index, event) {
    let value = this.seed ^ Math.imul(index + 1, 0x9e3779b1)
      ^ Math.imul(this.generation + 1, 0x85ebca6b) ^ Math.imul(event + 1, 0xc2b2ae35);
    value = Math.imul(value ^ (value >>> 16), 0x7feb352d);
    value = Math.imul(value ^ (value >>> 15), 0x846ca68b);
    return ((value ^ (value >>> 16)) >>> 0) / 4294967296;
  }

  #writeWind(targetX, targetY, index, x, y) {
    let speed = Math.hypot(x, y);
    if (!Number.isFinite(speed)) { x = 0; y = 0; speed = 0; }
    if (speed >= 1) { x /= speed; y /= speed; speed = 1; }
    if (speed < CALM_THRESHOLD) { x = 0; y = 0; }
    targetX[index] = x;
    targetY[index] = y;
  }
}
