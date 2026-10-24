import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import BackButton from '../components/BackButton';
import { useAppContext } from '../context/AppContext';
import type { CheckResponse } from '../types';
import styles from './BriefingPage.module.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

/** Convert "2025-12-01" + "14:00" → "2025-12-01T14:00:00" (local, no Z so the
 *  backend treats it as a naive hint rather than forcing UTC). */
function toFlightTime(date: string, time: string): string | null {
  if (!date || !time) return null;
  return `${date}T${time}:00`;
}

export default function BriefingPage() {
  const navigate = useNavigate();
  const { flightPlan } = useAppContext();

  const [response, setResponse] = useState<CheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!flightPlan) return;

    const params = new URLSearchParams();
    params.set('lat', String(flightPlan.location.lat));
    params.set('lon', String(flightPlan.location.lng));
    if (flightPlan.plannedAltitudeFt) params.set('planned_altitude_ft', String(flightPlan.plannedAltitudeFt));
    if (flightPlan.radiusMeters)      params.set('radius_m', String(flightPlan.radiusMeters));
    const ft = toFlightTime(flightPlan.date, flightPlan.time);
    if (ft) params.set('flight_time', ft);

    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/check?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`API error ${r.status}`);
        return r.json() as Promise<CheckResponse>;
      })
      .then(data => {
        setResponse(data);
        setLoading(false);
      })
      .catch(err => {
        setError(String(err));
        setLoading(false);
      });
  }, [flightPlan]);

  // Format the location / time header line
  const locationLabel = flightPlan?.location.displayName ?? '—';
  const dateLabel =
    flightPlan?.date
      ? new Date(`${flightPlan.date}T12:00:00`).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric', year: 'numeric',
        })
      : '';
  const timeLabel = flightPlan?.time ?? '';
  const subLabel = [dateLabel, timeLabel].filter(Boolean).join(' · ');

  return (
    <AppShell currentStep={3}>
      <div className={styles.page}>
        <BackButton to="/flight-plan" label="Back to Flight Plan" />

        {/* Header */}
        <div className={styles.pageHeader}>
          <h1 className={styles.title}>Flight Briefing</h1>
          <p className={styles.subtitle}>{locationLabel}{subLabel ? ` · ${subLabel}` : ''}</p>
        </div>

        {/* Single briefing box */}
        <section className={styles.section}>
          <div className={styles.briefingBox}>
            {loading && (
              <div className={styles.loadingState}>
                <span className={styles.spinner} aria-hidden="true" />
                <p>Skye is checking your flight conditions…</p>
              </div>
            )}

            {error && !loading && (
              <div className={styles.errorState}>
                <p className={styles.errorTitle}>Could not reach the Skye API</p>
                <p className={styles.errorDetail}>{error}</p>
                <p className={styles.errorDetail}>
                  Make sure the backend is running: <code>make run</code>
                </p>
              </div>
            )}

            {!flightPlan && !loading && (
              <p className={styles.emptyState}>No flight plan found. Go back and drop a pin.</p>
            )}

            {response && !loading && (
              <div className={styles.markdownOutput}>
                {/* Render the markdown as preformatted text — no external parser needed */}
                <MarkdownText text={response.answer_markdown} />

                {/* mock data notice */}
                {response.mock_data && (
                  <p className={styles.mockNotice}>
                    ⚠ Simulated or demo data was used in this briefing.
                  </p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* CTA */}
        {response && (
          <div className={styles.ctaRow}>
            <button className={styles.ctaButton} onClick={() => navigate('/lesson')}>
              Continue to Lesson →
            </button>
          </div>
        )}

        {/* Disclaimer */}
        <div className={styles.disclaimer}>
          <p>
            SkyBrief is an educational tool, not legal advice or FAA authorization. The pilot
            makes the final decision. Always verify in an FAA-approved app (e.g. B4UFLY) before
            flying.
          </p>
        </div>
      </div>
    </AppShell>
  );
}

// ---------------------------------------------------------------------------
// Minimal inline markdown renderer — no external deps.
// Handles: ## headings, **bold**, bullet lists, --- dividers, plain text.
// ---------------------------------------------------------------------------
function MarkdownText({ text }: { text: string }) {
  const lines = text.split('\n');

  return (
    <div className={styles.mdRoot}>
      {lines.map((line, i) => {
        if (/^#{1,3}\s/.test(line)) {
          const level = line.match(/^(#+)/)?.[1].length ?? 1;
          const content = line.replace(/^#+\s*/, '');
          if (level === 1) return <h2 key={i} className={styles.mdH1}>{inlineFormat(content)}</h2>;
          if (level === 2) return <h3 key={i} className={styles.mdH2}>{inlineFormat(content)}</h3>;
          return <h4 key={i} className={styles.mdH3}>{inlineFormat(content)}</h4>;
        }
        if (/^---+$/.test(line.trim())) return <hr key={i} className={styles.mdHr} />;
        if (/^[-*]\s/.test(line)) {
          return <p key={i} className={styles.mdBullet}>• {inlineFormat(line.replace(/^[-*]\s/, ''))}</p>;
        }
        if (line.trim() === '') return <div key={i} className={styles.mdBlank} />;
        return <p key={i} className={styles.mdPara}>{inlineFormat(line)}</p>;
      })}
    </div>
  );
}

/** Render **bold** and `code` inline spans. */
function inlineFormat(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`'))
      return <code key={i} className="inline-code">{part.slice(1, -1)}</code>;
    return part;
  });
}
