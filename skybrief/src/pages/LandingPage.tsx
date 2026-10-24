import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Wind, ChevronDown, Plane, Shield, BookOpen, MessageCircle } from 'lucide-react';
import AppShell from '../components/AppShell';
import NotReadyBanner from '../components/NotReadyBanner';
import dronePhoto from '../assets/drone-photo.jpg';
import { useAppContext } from '../context/AppContext';
import type { FlightPurpose, DroneWeightClass, ExperienceLevel, PilotProfile } from '../types';
import hero from './LandingPage.module.css';
import form from './PilotProfilePage.module.css';

// ── helpers (copied from PilotProfilePage) ───────────────────────────────────

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

// ── Feature cards ─────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Shield,
    title: 'Layered rules, explained',
    desc: 'Federal, California, and local rules decoded for your exact flight — not a generic checklist.',
  },
  {
    icon: Plane,
    title: 'Coaching, not just verdicts',
    desc: 'Wind, light, terrain, wildfire TFRs. Get a safer alternative when your spot has risks.',
  },
  {
    icon: BookOpen,
    title: 'Learn as you fly',
    desc: 'One rule taught per briefing with a quick quiz, so you build knowledge over time.',
  },
  {
    icon: MessageCircle,
    title: 'Ask Skye anytime',
    desc: 'Your AI flight coach answers only from official FAA and California sources.',
  },
];

// ── Starfield (deterministic pseudo-random, computed once at module load) ────

function makeStars(count: number) {
  let seed = 1337;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (seed % 10000) / 10000;
  };
  return Array.from({ length: count }, () => ({
    x: rand() * 100,
    y: rand() * 100,
    size: 1 + rand() * 1.6,
    delay: rand() * 4,
    duration: 2.5 + rand() * 3,
  }));
}

const STARS = makeStars(70);

// Shooting stars — occasional diagonal streaks, staggered so they never sync up.
const SHOOTING_STARS = [
  { x: 12, y: 8, delay: 0, duration: 6.5, tail: 110 },
  { x: 58, y: 4, delay: 2.4, duration: 7.5, tail: 90 },
  { x: 82, y: 14, delay: 4.8, duration: 5.5, tail: 130 },
  { x: 32, y: 22, delay: 1.2, duration: 8, tail: 100 },
  { x: 68, y: 28, delay: 3.6, duration: 6, tail: 80 },
  { x: 6, y: 34, delay: 5.6, duration: 7, tail: 120 },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { pilotProfile, setPilotProfile } = useAppContext();
  const heroRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const [headerVisible, setHeaderVisible] = useState(false);
  const [formVisible, setFormVisible] = useState(false);

  // Track when the hero section leaves the viewport → show sticky header
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => setHeaderVisible(!entry.isIntersecting),
      { threshold: 0.05 },
    );
    if (heroRef.current) observer.observe(heroRef.current);
    return () => observer.disconnect();
  }, []);

  // Animate the form section in when it enters the viewport
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setFormVisible(true); },
      { threshold: 0.08 },
    );
    if (formRef.current) observer.observe(formRef.current);
    return () => observer.disconnect();
  }, []);

  function scrollToForm() {
    formRef.current?.scrollIntoView({ behavior: 'smooth' });
  }

  // Land straight on the profile form when arriving via "Back to Profile"
  // from a later step — an instant jump, not an animated scroll, so it reads
  // as returning to a page rather than auto-scrolling down the landing page.
  useEffect(() => {
    if (location.hash === '#profile-form') {
      setFormVisible(true);
      formRef.current?.scrollIntoView({ behavior: 'auto', block: 'start' });
    }
  }, [location.hash]);

  // ── Pilot profile form state ───────────────────────────────────────────────
  const [purpose, setPurpose] = useState<FlightPurpose | null>(pilotProfile?.purpose ?? null);
  const [trustPassed, setTrustPassed] = useState(pilotProfile?.trustPassed ?? false);
  const [part107, setPart107] = useState(pilotProfile?.part107 ?? false);
  const [weight, setWeight] = useState<DroneWeightClass | null>(pilotProfile?.droneWeightClass ?? null);
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel | null>(
    pilotProfile?.experienceLevel ?? null,
  );

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
    <div className={hero.root}>

      {/* ── Sticky AppShell header (fades in after hero) ── */}
      <div className={`${hero.stickyHeader} ${headerVisible ? hero.stickyHeaderVisible : ''}`}>
        <AppShell currentStep={1} headerOnly />
      </div>

      {/* ══════════════════════════════════════════════
          HERO SECTION — fills 100vh
      ══════════════════════════════════════════════ */}
      <section ref={heroRef} className={hero.heroSection}>

        {/* Starfield */}
        <div className={hero.starfield} aria-hidden="true">
          {STARS.map((s, i) => (
            <span
              key={i}
              className={hero.star}
              style={{
                left: `${s.x}%`,
                top: `${s.y}%`,
                width: s.size,
                height: s.size,
                animationDelay: `${s.delay}s`,
                animationDuration: `${s.duration}s`,
              }}
            />
          ))}
        </div>

        {/* Shooting stars */}
        <div className={hero.shootingStars} aria-hidden="true">
          {SHOOTING_STARS.map((s, i) => (
            <span
              key={i}
              className={hero.shootingStar}
              style={{
                left: `${s.x}%`,
                top: `${s.y}%`,
                animationDelay: `${s.delay}s`,
                animationDuration: `${s.duration}s`,
                ['--tail-length' as string]: `${s.tail}px`,
              } as CSSProperties}
            />
          ))}
        </div>

        {/* Gradient orb */}
        <div className={hero.orbSecondary} aria-hidden="true" />

        {/* Large floating drone */}
        <div className={hero.droneWrap} aria-hidden="true">
          <img src={dronePhoto} alt="" className={hero.droneImg} />
        </div>

        {/* Hero content */}
        <div className={hero.heroContent}>
          {/* Wordmark */}
          <div className={hero.logoRow}>
            <div className={hero.logoIcon}>
              <Wind size={28} strokeWidth={2.5} />
            </div>
            <span className={hero.logoText}>SkyBrief</span>
          </div>
          
          {/* Headline */}
          <h1 className={hero.headline}>
            Your AI Agent for<br />
            <span className={hero.headlineAccent}>Safer Drone Usage</span>
          </h1>

          {/* Subheadline */}
          <p className={hero.subheadline}>
            SkyBrief checks federal, California, and local rules for your exact flight —
            explains them in plain language, coaches on real-world risk, and teaches you
            the rules as you go.
          </p>

          {/* Feature pills */}
          <div className={hero.featurePills}>
            {['FAA rules', 'CA state law', 'NPS & parks', 'Wind & light', 'Offline-ready'].map(f => (
              <span key={f} className={hero.pill}>{f}</span>
            ))}
          </div>

          {/* CTA */}
          <button className={hero.ctaButton} onClick={scrollToForm}>
            Start your flight brief
            <ChevronDown size={18} strokeWidth={2.5} className={hero.ctaChevron} />
          </button>

          {/* Scroll hint */}
          <div className={hero.scrollHint} aria-hidden="true">
            <div className={hero.scrollMouse}>
              <div className={hero.scrollWheel} />
            </div>
            <span>Scroll to begin</span>
          </div>
        </div>

      </section>

      {/* ══════════════════════════════════════════════
          CAPABILITIES — thin-divided grid below the hero
      ══════════════════════════════════════════════ */}
      <section className={hero.capabilitiesSection}>
        <div className={hero.capabilitiesInner}>
          <div className={hero.capabilitiesHeader}>
            <span className={hero.sectionEyebrow}>Capabilities</span>
            <h2 className={hero.sectionHeading}>Everything you need before you fly</h2>
            <p className={hero.sectionTagline}>
              Four checks, one verdict — built for beginner pilots flying in California.
            </p>
          </div>
          <div className={hero.capabilitiesGrid}>
            {FEATURES.map(({ icon: Icon, title, desc }, i) => (
              <div key={title} className={hero.capabilityCard}>
                <span className={hero.capabilityIndex}>{String(i + 1).padStart(2, '0')}</span>
                <div className={hero.capabilityIcon}>
                  <Icon size={20} strokeWidth={2} />
                </div>
                <p className={hero.capabilityTitle}>{title}</p>
                <p className={hero.capabilityDesc}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════
          FORM SECTION — scrolls in below hero
      ══════════════════════════════════════════════ */}
      <section
        ref={formRef}
        className={`${hero.formSection} ${formVisible ? hero.formSectionVisible : ''}`}
      >
        {/* Section header transition bridge */}
        <div className={hero.formBridge}>
          <div className={hero.bridgeLine} />
          <span className={hero.bridgeLabel}>
            <Wind size={14} strokeWidth={2.5} />
            Step 1 of 4 — Pilot Profile
          </span>
          <div className={hero.bridgeLine} />
        </div>

        {/* Pilot profile form */}
        <div className={form.page}>
          <h1 className={form.heading}>Tell us about yourself</h1>
          <p className={form.subheading}>
            We'll tailor your flight briefing to your pilot status and equipment.
          </p>

          {/* Section 1: Flight Purpose */}
          <section className={form.section}>
            <h2 className={form.sectionLabel}>Flight Purpose</h2>
            <div className={form.cardGrid}>
              <button
                type="button"
                className={`${form.radioCard} ${purpose === 'recreational' ? form.radioCardSelected : ''}`}
                onClick={() => { setPurpose('recreational'); setPart107(false); }}
                aria-pressed={purpose === 'recreational'}
              >
                <span className={form.radioCardTitle}>Recreational</span>
                <span className={form.radioCardDesc}>Flying for fun or hobby purposes.</span>
              </button>
              <button
                type="button"
                className={`${form.radioCard} ${purpose === 'commercial' ? form.radioCardSelected : ''}`}
                onClick={() => { setPurpose('commercial'); setTrustPassed(false); }}
                aria-pressed={purpose === 'commercial'}
              >
                <span className={form.radioCardTitle}>Commercial</span>
                <span className={form.radioCardDesc}>Paid work, business, or research flights.</span>
              </button>
            </div>
          </section>

          {/* Section 2: Certifications */}
          <section className={form.section}>
            <h2 className={form.sectionLabel}>Certifications</h2>
            <div className={form.checkboxGroup}>
              <label className={`${form.checkboxCard} ${trustPassed ? form.checkboxCardChecked : ''} ${purpose === 'commercial' ? form.checkboxCardDisabled : ''}`}>
                <input type="checkbox" className={form.hiddenCheckbox} checked={trustPassed} disabled={purpose === 'commercial'} onChange={e => setTrustPassed(e.target.checked)} />
                <span className={form.customCheckbox} aria-hidden="true">{trustPassed && '✓'}</span>
                <span className={form.checkboxLabel}>
                  I've passed the TRUST test
                  <span className={form.checkboxSub}>Required for all recreational fliers</span>
                </span>
              </label>
              <label className={`${form.checkboxCard} ${part107 ? form.checkboxCardChecked : ''} ${purpose === 'recreational' ? form.checkboxCardDisabled : ''}`}>
                <input type="checkbox" className={form.hiddenCheckbox} checked={part107} disabled={purpose === 'recreational'} onChange={e => setPart107(e.target.checked)} />
                <span className={form.customCheckbox} aria-hidden="true">{part107 && '✓'}</span>
                <span className={form.checkboxLabel}>
                  I hold a Part 107 certificate
                  <span className={form.checkboxSub}>Required for all commercial operations</span>
                </span>
              </label>
            </div>
            {showNotReady && <NotReadyBanner />}
          </section>

          {/* Section 3: Drone Weight */}
          <section className={form.section}>
            <h2 className={form.sectionLabel}>Drone Weight</h2>
            <div className={form.cardGrid}>
              <button
                type="button"
                className={`${form.radioCard} ${weight === 'under250g' ? form.radioCardSelected : ''}`}
                onClick={() => setWeight('under250g')}
                aria-pressed={weight === 'under250g'}
              >
                <span className={form.radioCardTitle}>Under 250 g</span>
                <span className={form.radioCardDesc}>e.g. DJI Mini 4 Pro, Mini 3 — no FAA registration needed.</span>
              </button>
              <button
                type="button"
                className={`${form.radioCard} ${weight === 'over250g' ? form.radioCardSelected : ''}`}
                onClick={() => setWeight('over250g')}
                aria-pressed={weight === 'over250g'}
              >
                <span className={form.radioCardTitle}>250 g or over</span>
                <span className={form.radioCardDesc}>e.g. DJI Air 3, Mavic 3 — FAA registration required.</span>
              </button>
            </div>
          </section>

          {/* Section 4: Experience Level */}
          <section className={form.section}>
            <h2 className={form.sectionLabel}>Experience Level</h2>
            <div className={form.cardGrid}>
              <button
                type="button"
                className={`${form.radioCard} ${experienceLevel === 'first-flight' ? form.radioCardSelected : ''}`}
                onClick={() => setExperienceLevel('first-flight')}
                aria-pressed={experienceLevel === 'first-flight'}
              >
                <span className={form.radioCardTitle}>First flight</span>
                <span className={form.radioCardDesc}>I haven't flown a drone before.</span>
              </button>
              <button
                type="button"
                className={`${form.radioCard} ${experienceLevel === 'some-experience' ? form.radioCardSelected : ''}`}
                onClick={() => setExperienceLevel('some-experience')}
                aria-pressed={experienceLevel === 'some-experience'}
              >
                <span className={form.radioCardTitle}>Some experience</span>
                <span className={form.radioCardDesc}>I've flown a handful of times.</span>
              </button>
              <button
                type="button"
                className={`${form.radioCard} ${experienceLevel === 'experienced' ? form.radioCardSelected : ''}`}
                onClick={() => setExperienceLevel('experienced')}
                aria-pressed={experienceLevel === 'experienced'}
              >
                <span className={form.radioCardTitle}>Experienced</span>
                <span className={form.radioCardDesc}>I fly regularly and know the basics.</span>
              </button>
            </div>
          </section>

          {/* Section 5: Requirements Summary */}
          <section className={form.section}>
            <h2 className={form.sectionLabel}>Your Requirements Summary</h2>
            <div className={form.summaryCard}>
              {summaryLines.map((line, i) => {
                const isWarning = line.startsWith('⚠');
                const isOk = line.startsWith('✓');
                return (
                  <p key={i} className={isWarning ? form.summaryLineWarn : isOk ? form.summaryLineOk : form.summaryLineMuted}>
                    {line}
                  </p>
                );
              })}
            </div>
          </section>

          {/* CTA */}
          <div className={form.ctaRow}>
            <button
              type="button"
              className={`${form.cta} ${!valid ? form.ctaDisabled : ''}`}
              disabled={!valid}
              onClick={handleSave}
            >
              Save Profile &amp; Continue →
            </button>
            {!valid && (
              <p className={form.ctaHint}>
                {!purpose ? 'Select a flight purpose to continue.'
                  : !weight ? 'Select your drone weight to continue.'
                  : !experienceLevel ? 'Select your experience level to continue.'
                  : purpose === 'recreational' && !trustPassed ? 'Pass TRUST before flying recreationally.'
                  : purpose === 'commercial' && !part107 ? 'A Part 107 certificate is required for commercial flights.'
                  : ''}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════
          FOOTER
      ══════════════════════════════════════════════ */}
      <footer className={hero.footer}>
        <div className={hero.footerTop}>
          <div className={hero.footerBrand}>
            <div className={hero.footerLogoRow}>
              <Wind size={18} strokeWidth={2.5} />
              <span>SkyBrief</span>
            </div>
            <p className={hero.footerTagline}>Your AI agent for safer drone usage.</p>
          </div>

          <div className={hero.footerCol}>
            <span className={hero.footerColLabel}>How It Works</span>
            <Link to="/" className={hero.footerLink}>01 — Pilot Profile</Link>
            <Link to="/flight-plan" className={hero.footerLink}>02 — Flight Plan</Link>
            <Link to="/briefing" className={hero.footerLink}>03 — Briefing</Link>
            <Link to="/lesson" className={hero.footerLink}>04 — Lesson</Link>
            <Link to="/chat" className={hero.footerLink}>Ask Skye</Link>
          </div>

          <div className={hero.footerCol}>
            <span className={hero.footerColLabel}>Resources</span>
            <a
              href="https://www.faa.gov/uas"
              target="_blank"
              rel="noopener noreferrer"
              className={hero.footerLink}
            >
              FAA UAS Resource Hub ↗
            </a>
            <p className={hero.footerNote}>
              Educational tool — not legal advice or FAA authorization. The pilot makes the final
              decision.
            </p>
          </div>

          <div className={hero.footerCol}>
            <span className={hero.footerColLabel}>About</span>
            <p className={hero.footerNote}>IBM AI Challenge — Responsible AI for Business &amp; Society</p>
          </div>
        </div>

        <div className={hero.footerBottom}>
          <span>© 2026 SkyBrief — educational prototype.</span>
          <span>Privacy-first · No account required</span>
        </div>
      </footer>
    </div>
  );
}
