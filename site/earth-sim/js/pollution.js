// Conservative donor-cell transport on the eight-neighbor torus.
// Each outgoing fraction depends only on the donor's OLD state. Receivers
// gather those exact fluxes, so no state beyond their immediate neighbors
// enters the next generation. Sources and sinks are applied by simulation.js.
export function transportPollution(pollution, temperature, windX, windY, neighbors, outgoing, target) {
  const size = pollution.length;
  for (let i = 0; i < size; i++) {
    const diffusion = Math.max(0, temperature[i] * 0.005
      - Math.sqrt(Math.min(255, pollution[i]) / 256) * 0.000029);
    for (let slot = 0; slot < 8; slot++) {
      const dx = slot < 3 ? slot - 1 : slot === 3 ? -1 : slot === 4 ? 1 : slot - 6;
      const dy = slot < 3 ? 1 : slot > 4 ? -1 : 0;
      const alignment = Math.max(0, (windX[i] * dx + windY[i] * dy) / Math.hypot(dx, dy));
      outgoing[i * 8 + slot] = (diffusion + alignment) / 9;
    }
    let total = 0;
    for (let slot = 0; slot < 8; slot++) total += outgoing[i * 8 + slot];
    if (total > 1) for (let slot = 0; slot < 8; slot++) outgoing[i * 8 + slot] /= total;
  }
  for (let i = 0; i < size; i++) {
    let retained = 1;
    let incoming = 0;
    for (let slot = 0; slot < 8; slot++) {
      retained -= outgoing[i * 8 + slot];
      const donor = neighbors[i * 8 + slot];
      incoming += pollution[donor] * outgoing[donor * 8 + 7 - slot];
    }
    target[i] = pollution[i] * Math.max(0, retained) + incoming;
  }
}
