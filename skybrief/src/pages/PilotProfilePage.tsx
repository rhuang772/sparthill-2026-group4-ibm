import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import NotReadyBanner from '../components/NotReadyBanner';
import { useAppContext } from '../context/AppContext';
import type { FlightPurpose, DroneWeightClass, ExperienceLevel, PilotProfile } from '../types';
import styles from './PilotProfilePage.module.css';

// ── helpers ──────────────────────────────────────────────────────────────────

function isFormValid(
  purpose: FlightPurpose | null,
  trustPassed: boolean,
  part107: boolean,
  weight: DroneWeightClass | null,
  experienceLevel: ExperienceLevel | null,
): boolean {
  if (!purpose || !weight || !experienceLevel) return false;
  if (purpose === 'recreational' && !trustPassed) return false;
  if (purpose === 'commercial' && !part107) return false;
  return true;
}

function buildSummaryLines(
  purpose: FlightPurpose | null,
  trustPassed: boolean,
  part107: boolean,
  weight: DroneWeightClass | null,
): string[] {
  const lines: string[] = [];
  if (!purpose && !weight) {
    lines.push('Make your selections above to see a personalized summary.');
    return lines;
  }

  if (purpose === 'recreational') {
    lines.push('✓ Flying for fun — TRUST certification applies.');
    if (!trustPassed) {
      lines.push('⚠ TRUST not yet passed — you must complete it before your first flight.');
    } else {
      lines.push('✓ TRUST passed — you meet the recreational knowledge requirement.');
    }
  }

  if (purpose === 'commercial') {
    lines.push('✓ Flying commercially — Part 107 rules apply.');
    if (part107) {
      lines.push('✓ Part 107 certificate held — you are authorized for commercial operations.');
    } else {
      lines.push('⚠ Part 107 certificate required for commercial operations.');
    }
  }

  if (weight === 'under250g') {
    lines.push('✓ Under 250 g — FAA registration not required.');
    lines.push('✓ Fly under 400 ft AGL in uncontrolled airspace.');
  } else if (weight === 'over250g') {
    lines.push('⚠ 250 g or over — FAA registration is required before flying.');
    lines.push('✓ Fly under 400 ft AGL in uncontrolled airspace.');
  }

  return lines;
}

// ── component ─────────────────────────────────────────────────────────────────

export default function PilotProfilePage() {
  const navigate = useNavigate();
  const { setPilotProfile } = useAppContext();

  const [purpose, setPurpose] = useState<FlightPurpose | null>(null);
  const [trustPassed, setTrustPassed] = useState(false);
  const [part107, setPart107] = useState(false);
  const [weight, setWeight] = useState<DroneWeightClass | null>(null);
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel | null>(null);

  const showNotReady = purpose === 'recreational' && !trustPassed;
  const valid = isFormValid(purpose, trustPassed, part107, weight, experienceLevel);
  const summaryLines = buildSummaryLines(purpose, trustPassed, part107, weight);

  function handleSave() {
    if (!purpose || !weight || !experienceLevel) return;
    const profile: PilotProfile = {
      purpose,
      trustPassed,
      part107,
      droneWeightClass: weight,
      experienceLevel,
    };
    setPilotProfile(profile);
    navigate('/flight-plan');
  }

  return (
    <AppShell currentStep={1}>
      <div className={styles.page}>
        <h1 className={styles.heading}>Tell us about yourself</h1>
        <p className={styles.subheading}>
          We'll tailor your flight briefing to your pilot status and equipment.
        </p>

        {/* ── Section 1: Flight Purpose ── */}
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Flight Purpose</h2>
          <div className={styles.cardGrid}>
            <button
              type="button"
              className={`${styles.radioCard} ${purpose === 'recreational' ? styles.radioCardSelected : ''}`}
              onClick={() => {
                setPurpose('recreational');
                setPart107(false);
              }}
              aria-pressed={purpose === 'recreational'}
            >
              <span className={styles.radioCardTitle}>Recreational</span>
              <span className={styles.radioCardDesc}>Flying for fun or hobby purposes.</span>
            </button>

            <button
              type="button"
              className={`${styles.radioCard} ${purpose === 'commercial' ? styles.radioCardSelected : ''}`}
              onClick={() => {
                setPurpose('commercial');
                setTrustPassed(false);
              }}
              aria-pressed={purpose === 'commercial'}
            >
              <span className={styles.radioCardTitle}>Commercial</span>
              <span className={styles.radioCardDesc}>Paid work, business, or research flights.</span>
            </button>
          </div>
        </section>

        {/* ── Section 2: Certifications ── */}
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Certifications</h2>
          <div className={styles.checkboxGroup}>
            <label
              className={`${styles.checkboxCard} ${trustPassed ? styles.checkboxCardChecked : ''} ${
                purpose === 'commercial' ? styles.checkboxCardDisabled : ''
              }`}
            >
              <input
                type="checkbox"
                className={styles.hiddenCheckbox}
                checked={trustPassed}
                disabled={purpose === 'commercial'}
                onChange={(e) => setTrustPassed(e.target.checked)}
              />
              <span className={styles.customCheckbox} aria-hidden="true">
                {trustPassed && '✓'}
              </span>
              <span className={styles.checkboxLabel}>
                I've passed the TRUST test
                <span className={styles.checkboxSub}>
                  Required for all recreational fliers
                </span>
              </span>
            </label>

            <label
              className={`${styles.checkboxCard} ${part107 ? styles.checkboxCardChecked : ''} ${
                purpose === 'recreational' ? styles.checkboxCardDisabled : ''
              }`}
            >
              <input
                type="checkbox"
                className={styles.hiddenCheckbox}
                checked={part107}
                disabled={purpose === 'recreational'}
                onChange={(e) => setPart107(e.target.checked)}
              />
              <span className={styles.customCheckbox} aria-hidden="true">
                {part107 && '✓'}
              </span>
              <span className={styles.checkboxLabel}>
                I hold a Part 107 certificate
                <span className={styles.checkboxSub}>
                  Required for all commercial operations
                </span>
              </span>
            </label>
          </div>

          {showNotReady && <NotReadyBanner />}
        </section>

        {/* ── Section 3: Drone Weight ── */}
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Drone Weight</h2>
          <div className={styles.cardGrid}>
            <button
              type="button"
              className={`${styles.radioCard} ${weight === 'under250g' ? styles.radioCardSelected : ''}`}
              onClick={() => setWeight('under250g')}
              aria-pressed={weight === 'under250g'}
            >
              <span className={styles.radioCardTitle}>Under 250 g</span>
              <span className={styles.radioCardDesc}>
                e.g. DJI Mini 4 Pro, Mini 3 — no FAA registration needed.
              </span>
            </button>

            <button
              type="button"
              className={`${styles.radioCard} ${weight === 'over250g' ? styles.radioCardSelected : ''}`}
              onClick={() => setWeight('over250g')}
              aria-pressed={weight === 'over250g'}
            >
              <span className={styles.radioCardTitle}>250 g or over</span>
              <span className={styles.radioCardDesc}>
                e.g. DJI Air 3, Mavic 3 — FAA registration required.
              </span>
            </button>
          </div>
        </section>

        {/* ── Section 4: Experience Level ── */}
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Experience Level</h2>
          <div className={styles.cardGrid}>
            <button
              type="button"
              className={`${styles.radioCard} ${experienceLevel === 'first-flight' ? styles.radioCardSelected : ''}`}
              onClick={() => setExperienceLevel('first-flight')}
              aria-pressed={experienceLevel === 'first-flight'}
            >
              <span className={styles.radioCardTitle}>First flight</span>
              <span className={styles.radioCardDesc}>I haven't flown a drone before.</span>
            </button>

            <button
              type="button"
              className={`${styles.radioCard} ${experienceLevel === 'some-experience' ? styles.radioCardSelected : ''}`}
              onClick={() => setExperienceLevel('some-experience')}
              aria-pressed={experienceLevel === 'some-experience'}
            >
              <span className={styles.radioCardTitle}>Some experience</span>
              <span className={styles.radioCardDesc}>I've flown a handful of times.</span>
            </button>

            <button
              type="button"
              className={`${styles.radioCard} ${experienceLevel === 'experienced' ? styles.radioCardSelected : ''}`}
              onClick={() => setExperienceLevel('experienced')}
              aria-pressed={experienceLevel === 'experienced'}
            >
              <span className={styles.radioCardTitle}>Experienced</span>
              <span className={styles.radioCardDesc}>I fly regularly and know the basics.</span>
            </button>
          </div>
        </section>

        {/* ── Section 5: Requirements Summary ── */}
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Your Requirements Summary</h2>
          <div className={styles.summaryCard}>
            {summaryLines.map((line, i) => {
              const isWarning = line.startsWith('⚠');
              const isOk = line.startsWith('✓');
              return (
                <p
                  key={i}
                  className={
                    isWarning
                      ? styles.summaryLineWarn
                      : isOk
                      ? styles.summaryLineOk
                      : styles.summaryLineMuted
                  }
                >
                  {line}
                </p>
              );
            })}
          </div>
        </section>

        {/* ── CTA ── */}
        <div className={styles.ctaRow}>
          <button
            type="button"
            className={`${styles.cta} ${!valid ? styles.ctaDisabled : ''}`}
            disabled={!valid}
            onClick={handleSave}
          >
            Save Profile &amp; Continue →
          </button>
          {!valid && (
            <p className={styles.ctaHint}>
              {!purpose
                ? 'Select a flight purpose to continue.'
                : !weight
                ? 'Select your drone weight to continue.'
                : !experienceLevel
                ? 'Select your experience level to continue.'
                : purpose === 'recreational' && !trustPassed
                ? 'Pass TRUST before flying recreationally.'
                : purpose === 'commercial' && !part107
                ? 'A Part 107 certificate is required for commercial flights.'
                : ''}
            </p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
