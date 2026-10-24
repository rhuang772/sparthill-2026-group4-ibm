import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import BackButton from '../components/BackButton';
import VerdictCard from '../components/VerdictCard';
import RulesAccordion from '../components/RulesAccordion';
import RiskFactorCard from '../components/RiskFactorCard';
import AlternativeSuggestion from '../components/AlternativeSuggestion';
import { mockBriefing, mockBriefingNoGo } from '../data/mockBriefing';
import { isNearSJCAirspace } from '../utils/caScope';
import { useAppContext } from '../context/AppContext';
import styles from './BriefingPage.module.css';

export default function BriefingPage() {
  const navigate = useNavigate();
  const { flightPlan } = useAppContext();

  // Pick the demo scenario from the planned location: a pin inside the SJC
  // Class C demo boundary shows the No-Go scenario; everything else falls
  // back to the Caution scenario (Coyote Lake).
  const pack =
    flightPlan && isNearSJCAirspace(flightPlan.location.lat, flightPlan.location.lng)
      ? mockBriefingNoGo
      : mockBriefing;

  const { locationLabel, dateTimeLabel, verdict, findings, riskFactors, alternative, generatedAt } = pack;

  // Format the generated timestamp for display
  const generatedDate = new Date(generatedAt).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });

  return (
    <AppShell currentStep={3}>
      <div className={styles.page}>
        <BackButton to="/flight-plan" label="Back to Flight Plan" />

        {/* Page title */}
        <div className={styles.pageHeader}>
          <h1 className={styles.title}>Flight Briefing</h1>
          <p className={styles.subtitle}>
            {locationLabel} · {dateTimeLabel}
          </p>
          <p className={styles.generatedAt}>Generated {generatedDate}</p>
        </div>

        {/* Verdict */}
        <section className={styles.section}>
          <VerdictCard verdict={verdict} />
        </section>

        {/* Layered Rules */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Applicable Rules</h2>
          <RulesAccordion findings={findings} />
        </section>

        {/* Risk Factors */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Risk Factors</h2>
          <div className={styles.riskGrid}>
            {riskFactors.map((factor) => (
              <RiskFactorCard key={factor.type} factor={factor} />
            ))}
          </div>
        </section>

        {/* Alternative Location */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Alternative Location</h2>
          <AlternativeSuggestion alternative={alternative} />
        </section>

        {/* CTA */}
        <div className={styles.ctaRow}>
          <button
            className={styles.ctaButton}
            onClick={() => navigate('/lesson')}
          >
            Continue to Lesson →
          </button>
        </div>

        {/* Disclaimer */}
        <div className={styles.disclaimer}>
          <p>
            SkyBrief is an educational tool, not legal advice or FAA authorization. The pilot makes
            the final decision.
          </p>
        </div>

      </div>
    </AppShell>
  );
}
