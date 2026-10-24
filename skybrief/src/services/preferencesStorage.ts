const PROFILE_KEY = 'skybrief:pilotProfile';
const PLAN_KEY = 'skybrief:flightPlan';

export function clearPrivateData(): void {
  localStorage.removeItem(PROFILE_KEY);
  localStorage.removeItem(PLAN_KEY);
}

export function readPreferences<T>(kind: 'profile' | 'flightPlan'): T | null {
  const key = kind === 'profile' ? PROFILE_KEY : PLAN_KEY;
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : null;
  } catch { return null; }
}
export function savePreferences<T>(kind: 'profile' | 'flightPlan', value: T): void {
  localStorage.setItem(kind === 'profile' ? PROFILE_KEY : PLAN_KEY, JSON.stringify(value));
}
