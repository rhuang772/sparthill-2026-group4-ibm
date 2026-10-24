import { useState, useEffect }from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import BackButton from '../components/BackButton';
import { useAppContext } from '../context/AppContext';
import type { CheckResponse } from '../types';
import { mockBriefing, mockBriefingNoGo } from '../data/mockBriefing';
import { isNearSJCAirspace } from '../utils/caScope';
import { downloadDemoBriefingPdf } from '../services/briefingPdf';
import styles from './BriefingPage.module.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
const ASSESSMENT_LABELS = {
  go: 'Go — no blockers identified in checked sources',
  caution: 'Caution — review the findings before deciding',
  no_go: 'No-go — a source-based blocker was identified',
} as const;
const ASSESSMENT_STYLES = {
  go: styles.assessmentGo,
  caution: styles.assessmentCaution,
  no_go: styles.assessmentNoGo,
} as const;
const BRIEFING_SECTIONS = [
  { key: 'airspace', title: 'Airspace & authorization' },
  { key: 'conditions', title: 'Flight conditions' },
  { key: 'restrictions', title: 'Restrictions' },
  { key: 'nearby_risks', title: 'Nearby risks' },
] as const;

/** Convert the locally entered flight date/time to the UTC ISO format used by the APIs. */
function toFlightTime(date: string, time: string): string | null {
  if (!date || !time) return null;
  return new Date(`${date}T${time}:00`).toISOString();
}

export default function BriefingPage() {
  const navigate = useNavigate();
  const { flightPlan } = useAppContext();
  const [saveMessage, setSaveMessage] = useState('');

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
    if (ft) params.set('start', ft);

    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/briefing?${params}`)
      .then(r => {
        if (!r.ok) {
          return r.text().then(detail => {
            throw new Error(`API error ${r.status}: ${detail}`);
          });
        }
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

  // The PDF button exports a clearly labeled demo scenario, not live API data.
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
                {response.flight_assessment && (
                  <aside
                    className={`${styles.assessment} ${ASSESSMENT_STYLES[response.flight_assessment]}`}
                    role="status"
                    aria-label="Advisory flight assessment"
                  >
                    <h2 className={styles.assessmentTitle}>
                      {ASSESSMENT_LABELS[response.flight_assessment]}
                    </h2>
                    {response.assessment_summary && <p>{response.assessment_summary}</p>}
                    <p className={styles.assessmentDisclaimer}>
                      Advisory only—not FAA authorization or a guarantee of safety. Verify in B4UFLY and check current NOTAMs.
                    </p>
                  </aside>
                )}
                {response.section_summaries ? (
                  <div className={styles.briefingSections}>
                    {BRIEFING_SECTIONS.map((section) => {
                      const facts = response.flight_facts?.filter(
                        (fact) => fact.section === section.key,
                      ) ?? [];
                      const summary = response.section_summaries?.[section.key];
                      return (
                        <section className={styles.facts} key={section.key}>
                          <h2 className={styles.factsTitle}>{section.title}</h2>
                          {facts.length > 0 && (
                            <dl className={styles.factsList}>
                              {facts.map((fact) => (
                                <div className={styles.fact} key={fact.label}>
                                  <dt>{fact.label}</dt>
                                  <dd>{fact.value}</dd>
                                  <dd className={styles.factSource}>
                                    {fact.source}{fact.checked_at ? ` · Checked ${fact.checked_at}` : ''}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          )}
                          {summary && (
                            <p className={styles.sectionSummary}>
                              <strong>Summary:</strong> {summary}
                            </p>
                          )}
                        </section>
                      );
                    })}
                  </div>
                ) : (
                  <MarkdownText text={response.answer_markdown} />
                )}

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
          <button className={styles.ctaButton} onClick={() => {
            try {
              downloadDemoBriefingPdf(pack, flightPlan);
              setSaveMessage('Demo briefing PDF downloaded.');
            } catch {
              setSaveMessage('Unable to create the demo briefing PDF.');
            }
          }}>Save this demo briefing offline (PDF)</button>
          <p role="status">{saveMessage}</p>
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
