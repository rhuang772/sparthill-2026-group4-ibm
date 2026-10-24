/** Conservative UI policy only: stale or unknown data must never be presented as a current Go. */
export const WEATHER_MAX_AGE_MS = 60 * 60 * 1000;
export const FAA_MAX_AGE_MS = 24 * 60 * 60 * 1000;
export function isStale(fetchedAt: string | undefined, maxAgeMs: number, now = Date.now()): boolean {
  if (!fetchedAt) return true;
  const then = Date.parse(fetchedAt);
  return !Number.isFinite(then) || then > now || now - then > maxAgeMs;
}
export function offlineStatus(weatherTime?: string, faaTime?: string, now = Date.now()): 'caution' | 'unverified' {
  return isStale(weatherTime, WEATHER_MAX_AGE_MS, now) || isStale(faaTime, FAA_MAX_AGE_MS, now) ? 'caution' : 'unverified';
}
