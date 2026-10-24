import '../utils/leafletIconFix'; // side-effect: fixes Leaflet marker icons in Vite
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Circle, useMapEvents } from 'react-leaflet';
import type { LatLng } from 'leaflet';
import { ArrowRight, MapPin } from 'lucide-react';
import AppShell from '../components/AppShell';
import BackButton from '../components/BackButton';
import OutOfScopeBanner from '../components/OutOfScopeBanner';
import { isInCalifornia } from '../utils/caScope';
import { useAppContext } from '../context/AppContext';
import styles from './FlightPlanPage.module.css';

// ── Internal: listens for map clicks and raises them to the parent ────────
function MapClickHandler({ onMapClick }: { onMapClick: (latlng: LatLng) => void }) {
  useMapEvents({
    click(e) {
      onMapClick(e.latlng);
    },
  });
  return null;
}

// ── Coordinate formatting helpers ─────────────────────────────────────────
function formatLat(lat: number): string {
  return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}`;
}
function formatLng(lng: number): string {
  return `${Math.abs(lng).toFixed(4)}°${lng >= 0 ? 'E' : 'W'}`;
}

// ── Page ─────────────────────────────────────────────────────────────────
export default function FlightPlanPage() {
  const navigate = useNavigate();
  const { flightPlan: existingPlan, setFlightPlan } = useAppContext();

  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(
    existingPlan ? { lat: existingPlan.location.lat, lng: existingPlan.location.lng } : null,
  );
  const [date, setDate] = useState(existingPlan?.date ?? '');
  const [time, setTime] = useState(existingPlan?.time ?? '');
  const [altitude, setAltitude] = useState(
    existingPlan ? String(existingPlan.plannedAltitudeFt) : '100',
  );
  const [radius, setRadius] = useState(
    existingPlan ? String(existingPlan.radiusMeters) : '100',
  );

  const inCa = pin ? isInCalifornia(pin.lat, pin.lng) : true; // no warning until pin placed
  const altitudeValue = Number(altitude);
  const altitudeValid = altitude !== '' && Number.isFinite(altitudeValue) && altitudeValue > 0;
  const radiusValue = Number(radius);
  const radiusValid = radius !== '' && Number.isFinite(radiusValue) && radiusValue > 0;
  const canSubmit = pin !== null && inCa && altitudeValid && radiusValid;

  function handleMapClick(latlng: LatLng) {
    setPin({ lat: latlng.lat, lng: latlng.lng });
  }

  function handleSubmit() {
    if (!pin || !altitudeValid || !radiusValid) return;
    setFlightPlan({
      location: {
        lat: pin.lat,
        lng: pin.lng,
        displayName: `${formatLat(pin.lat)}, ${formatLng(pin.lng)}`,
      },
      date,
      time,
      plannedAltitudeFt: altitudeValue,
      radiusMeters: radiusValue,
    });
    navigate('/briefing');
  }

  return (
    <AppShell currentStep={2}>
      <div className={styles.page}>
        <BackButton to="/#profile-form" label="Back to Profile" />
        <div className={styles.layout}>

          {/* ── Left: Map ──────────────────────────────────────────────── */}
          <div className={styles.mapColumn}>
            <p className={styles.mapHeading}>Click anywhere on the map to drop a pin</p>
            <div className={styles.mapWrapper}>
              <MapContainer
                center={pin ? [pin.lat, pin.lng] : [37.5, -119.5]}
                zoom={pin ? 11 : 6}
                style={{ width: '100%', height: '100%' }}
                scrollWheelZoom
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <MapClickHandler onMapClick={handleMapClick} />
                {pin && <Marker position={[pin.lat, pin.lng]} />}
                {pin && radiusValid && (
                  <Circle
                    center={[pin.lat, pin.lng]}
                    radius={radiusValue}
                    pathOptions={{ color: '#0F766E', fillColor: '#0F766E', fillOpacity: 0.12, weight: 2 }}
                  />
                )}
              </MapContainer>
            </div>

            {pin ? (
              <p className={styles.mapCaption}>
                Selected:{' '}
                <span className={styles.mapCaptionCoords}>
                  {formatLat(pin.lat)}, {formatLng(pin.lng)}
                </span>
              </p>
            ) : (
              <p className={styles.mapCaption}>No location selected</p>
            )}
          </div>

          {/* ── Right: Controls panel ───────────────────────────────────── */}
          <div className={styles.panel}>

            {/* Flight Location */}
            <div>
              <p className={styles.sectionLabel}>
                <MapPin size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Flight Location
              </p>
              <div className={styles.locationBlock}>
                {pin ? (
                  <>
                    <p className={styles.locationCoords}>
                      {formatLat(pin.lat)}, {formatLng(pin.lng)}
                    </p>
                    <p className={styles.locationSub}>
                      {inCa ? 'Within California ✓' : 'Outside California'}
                    </p>
                  </>
                ) : (
                  <p className={styles.locationPlaceholder}>
                    Click the map to select a location
                  </p>
                )}
              </div>

              {/* Out-of-scope warning */}
              {pin && !inCa && <OutOfScopeBanner />}
            </div>

            {/* Date & Time */}
            <div className={styles.fieldGroup}>
              <div className={styles.field}>
                <label className={styles.fieldLabel} htmlFor="flight-date">
                  Flight Date
                </label>
                <input
                  id="flight-date"
                  type="date"
                  className={styles.fieldInput}
                  value={date}
                  onChange={e => setDate(e.target.value)}
                />
              </div>

              <div className={styles.field}>
                <label className={styles.fieldLabel} htmlFor="takeoff-time">
                  Takeoff Time
                </label>
                <input
                  id="takeoff-time"
                  type="time"
                  className={styles.fieldInput}
                  value={time}
                  onChange={e => setTime(e.target.value)}
                />
              </div>

              <div className={styles.field}>
                <label className={styles.fieldLabel} htmlFor="planned-altitude">
                  Planned Altitude (ft AGL)
                </label>
                <input
                  id="planned-altitude"
                  type="number"
                  min={1}
                  step={1}
                  className={styles.fieldInput}
                  value={altitude}
                  onChange={e => setAltitude(e.target.value)}
                />
                {!altitudeValid && (
                  <p className={styles.fieldHint}>Enter the altitude you plan to fly at, in feet.</p>
                )}
              </div>

              <div className={styles.field}>
                <label className={styles.fieldLabel} htmlFor="flight-radius">
                  Flight Area Radius (m)
                </label>
                <input
                  id="flight-radius"
                  type="number"
                  min={1}
                  step={1}
                  className={styles.fieldInput}
                  value={radius}
                  onChange={e => setRadius(e.target.value)}
                />
                {!radiusValid && (
                  <p className={styles.fieldHint}>
                    Enter how far from the pin you plan to fly, in meters.
                  </p>
                )}
              </div>
            </div>

            {/* CTA */}
            <button
              className={`${styles.ctaButton} ${canSubmit ? styles.ctaEnabled : styles.ctaDisabled}`}
              disabled={!canSubmit}
              onClick={handleSubmit}
              aria-disabled={!canSubmit}
            >
              Plan This Flight
              <ArrowRight size={16} strokeWidth={2.5} />
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
