import { useState, useEffect }from 'react';
import { saveBriefing } from '../services/offlineStorage';
import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import BackButton from '../components/BackButton';
import { useAppContext } from '../context/AppContext';
import { streamSkye, type StreamTool } from '../services/skyeStream';
import type { CheckResponse } from '../types';
import { mockBriefing, mockBriefingNoGo } from '../data/mockBriefing';
import { isNearSJCAirspace } from '../utils/caScope';
import styles from './BriefingPage.module.css';

/** Convert "2025-12-01" + "14:00" → "2025-12-01T14:00:00" (local, no Z so the
 *  backend treats it as a naive hint rather than forcing UTC). */
function toFlightTime(date: string, time: string): string | null {
  if (!date || !time) return null;
  return `${date}T${time}:00`;
}

export default function BriefingPage() {
  const navigate = useNavigate();
  const { flightPlan } = useAppContext();
  const [saveMessage, setSaveMessage] = useState('');

  const [response, setResponse] = useState<CheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamText, setStreamText] = useState('');
  const [statusText, setStatusText] = useState<string | null>(null);
  const [tools, setTools] = useState<StreamTool[]>([]);

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
    setResponse(null);
    setStreamText('');
    setStatusText(null);
    setTools([]);

    const controller = new AbortController();
    streamSkye<CheckResponse>('/check/stream', params, {
      onStatus: setStatusText,
      onTool: tool =>
        setTools(prev => [...prev.filter(t => t.name !== tool.name), tool]),
      onReset: () => setStreamText(''),
      onToken: chunk => setStreamText(prev => prev + chunk),
      onDone: data => {
        setResponse(data);
        setLoading(false);
      },
    }, controller.signal).catch(err => {
      if (controller.signal.aborted) return;
      setError(String(err));
      setLoading(false);
    });

    return () => controller.abort();
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

  // The "save offline" demo button stores the canned mock scenario (not the
  // live API response) — it's explicitly a demo artifact, picked the same
  // way the old mock-only BriefingPage chose between its two scenarios.
  const pack =
    flightPlan && isNearSJCAirspace(flightPlan.location.lat, flightPlan.location.lng)
      ? mockBriefingNoGo
      : mockBriefing;

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
            {loading && !streamText && (
              <div className={styles.loadingState}>
                <span className={styles.spinner} aria-hidden="true" />
                <p>{statusText ?? 'Skye is checking your flight conditions…'}</p>
                {tools.length > 0 && (
                  <ul className={styles.toolList}>
                    {tools.map(t => (
                      <li key={t.name} className={styles.toolItem}>
                        {t.state === 'running' ? '…' : t.status === 'ok' ? '✓' : '⚠'} {t.label}
                        {t.state === 'done' && t.status !== 'ok' && ` (${t.status})`}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {loading && streamText && (
              <div className={styles.markdownOutput} aria-live="polite">
                <MarkdownText text={streamText} />
                <span className={styles.caret} aria-hidden="true" />
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

        <section className={styles.section}>
          <p role="status" style={{marginBottom: '0.75rem'}}>Demo scenario only — these findings are mocked, not a live safety or authorization check.</p>
          <button className={styles.ctaButton} onClick={async () => {
            try {
              await saveBriefing({ briefing: pack, flightPlan, demo: true });
              setSaveMessage('Demo briefing saved on this device.');
            } catch { setSaveMessage('Unable to save locally. Check browser storage settings.'); }
          }}>Save this demo briefing offline</button>
          <p role="status">{saveMessage}</p>
          <p><a href="/saved">View saved briefings &amp; privacy settings</a></p>
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
