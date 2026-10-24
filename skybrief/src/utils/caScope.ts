/**
 * Returns true when the given coordinates fall within California's
 * approximate bounding box.
 *
 * Bounding box:
 *   Latitude:   32.5° N  –  42.0° N
 *   Longitude: -124.5° W – -114.1° W
 */
export function isInCalifornia(lat: number, lng: number): boolean {
  return lat >= 32.5 && lat <= 42.0 && lng >= -124.5 && lng <= -114.1;
}

/**
 * Returns true when the given coordinates fall inside the demo bounding box
 * around Mineta San José International Airport (SJC) and SJSU, used to
 * trigger the No-Go / controlled-airspace demo scenario. This is a mocked
 * stand-in for real Class C surface-area geometry.
 */
export function isNearSJCAirspace(lat: number, lng: number): boolean {
  return lat >= 37.3 && lat <= 37.4 && lng >= -121.97 && lng <= -121.85;
}
