export interface ViewportWindow {
  start: number;
  end: number;
}

export function calculateViewport(total: number, zoom: number, pan: number, minWindow = 20): ViewportWindow {
  const windowSize = Math.max(minWindow, Math.floor(total / Math.max(1, zoom)));
  const maxStart = Math.max(0, total - windowSize);
  const start = Math.min(maxStart, Math.max(0, Math.floor(pan * maxStart)));
  return { start, end: Math.min(total, start + windowSize) };
}

