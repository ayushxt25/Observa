export function scheduleFrame(previous: number | null, draw: () => void): number {
  if (previous !== null) cancelAnimationFrame(previous);
  return requestAnimationFrame(draw);
}

