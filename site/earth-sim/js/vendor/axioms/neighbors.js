/** Toroidal Moore neighborhood. Slots NW,N,NE,W,E,SW,S,SE are part of the contract. */
export function mooreNeighbors(width, height) {
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1 || width * height > 16000000) throw new RangeError("Unsupported grid dimensions");
    const table = new Int32Array(width * height * 8);
    const offsets = [[-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]];
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const index = y * width + x;
        offsets.forEach(([dx, dy], slot) => {
          const nx = (x + dx + width) % width;
          const ny = (y + dy + height) % height;
          table[index * 8 + slot] = ny * width + nx;
        });
      }
    }
    return table;
  }
