export function linearScale(domainMin: number, domainMax: number, rangeMin: number, rangeMax: number): (value: number) => number {
  const domain = Math.max(1, domainMax - domainMin);
  return (value: number) => rangeMin + ((value - domainMin) / domain) * (rangeMax - rangeMin);
}

