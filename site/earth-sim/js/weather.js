// Positive X is east; positive Y is north, opposite to canvas/grid row Y.
export const NEIGHBOR_X = [-1, 0, 1, -1, 1, -1, 0, 1];
export const NEIGHBOR_Y = [1, 1, 1, 0, 0, -1, -1, -1];

// Stochastic upwind sampling of a categorical cloud field. Shared per-tick
// samples translate a uniform-flow cloud bank intact, rather than independently
// flickering its cells. Fractional speed controls the probability of movement.
// Only the receiver's old wind and one immediate old neighbor are read.
export function advectedCloud(index, clouds, windX, windY, neighbors, sampleX, sampleY) {
  const dx = sampleX < Math.abs(windX[index]) ? -Math.sign(windX[index]) : 0;
  const dy = sampleY < Math.abs(windY[index]) ? -Math.sign(windY[index]) : 0;
  if (dx === 0 && dy === 0) return clouds[index];
  const position = (1 - dy) * 3 + dx + 1;
  const slot = position < 4 ? position : position - 1;
  return clouds[neighbors[index * 8 + slot]];
}
