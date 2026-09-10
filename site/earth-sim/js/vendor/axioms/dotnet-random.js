/**
 * The subtractive PRNG used by .NET Framework's System.Random.
 * Keeping it here makes the 2012 seed values meaningful in the browser.
 */
export class DotNetRandom {
  static MBIG = 2147483647;
  static MSEED = 161803398;

  constructor(seed = 0) {
    const subtraction = seed === -2147483648 ? 2147483647 : Math.abs(seed | 0);
    let mj = DotNetRandom.MSEED - subtraction;
    if (mj < 0) mj += DotNetRandom.MBIG;

    this.seedArray = new Int32Array(56);
    this.seedArray[55] = mj;
    let mk = 1;

    for (let i = 1; i < 55; i += 1) {
      const ii = (21 * i) % 55;
      this.seedArray[ii] = mk;
      mk = mj - mk;
      if (mk < 0) mk += DotNetRandom.MBIG;
      mj = this.seedArray[ii];
    }

    for (let pass = 1; pass < 5; pass += 1) {
      for (let i = 1; i < 56; i += 1) {
        this.seedArray[i] -= this.seedArray[1 + ((i + 30) % 55)];
        if (this.seedArray[i] < 0) this.seedArray[i] += DotNetRandom.MBIG;
      }
    }

    this.inext = 0;
    this.inextp = 21;
  }

  sample() {
    this.inext += 1;
    if (this.inext >= 56) this.inext = 1;
    this.inextp += 1;
    if (this.inextp >= 56) this.inextp = 1;

    let value = this.seedArray[this.inext] - this.seedArray[this.inextp];
    if (value === DotNetRandom.MBIG) value -= 1;
    if (value < 0) value += DotNetRandom.MBIG;
    this.seedArray[this.inext] = value;
    return value * (1 / DotNetRandom.MBIG);
  }

  nextDouble() {
    return this.sample();
  }

  next(maxExclusive = DotNetRandom.MBIG) {
    if (!Number.isInteger(maxExclusive) || maxExclusive <= 0) {
      throw new RangeError("maxExclusive must be a positive integer");
    }
    return Math.floor(this.sample() * maxExclusive);
  }
}

export function normalizeSeed(value) {
  if (!Number.isFinite(value)) return 0;
  const integer = Math.trunc(value);
  return integer > 2147483647 || integer < -2147483648 ? integer | 0 : integer;
}
