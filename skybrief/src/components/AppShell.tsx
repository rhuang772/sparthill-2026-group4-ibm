import { useNavigate, useLocation } from 'react-router-dom';
import { Wind, Check, Bot } from 'lucide-react';
import shellStyles from './AppShell.module.css';

interface Step {
  number: number;
  label: string;
  path: string;
}

// Skye is now a persistent tab — not part of the numbered flow
const STEPS: Step[] = [
  { number: 1, label: 'Profile',     path: '/'            },
  { number: 2, label: 'Flight Plan', path: '/flight-plan' },
  { number: 3, label: 'Briefing',    path: '/briefing'    },
  { number: 4, label: 'Lesson',      path: '/lesson'      },
];

interface AppShellProps {
  currentStep: number;   // 1–4; pass 0 on the Skye page
  children?: React.ReactNode;
  /** Render only the sticky <header> bar with no shell wrapper or <main>.
   *  Used by LandingPage to overlay the header after the hero scrolls away. */
  headerOnly?: boolean;
}

export default function AppShell({ currentStep, children, headerOnly }: AppShellProps) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const onSkyePage = pathname === '/chat';

  const header = (
    <header className={shellStyles.header}>
        {/* Wordmark */}
        <button
          className={shellStyles.wordmark}
          onClick={() => navigate('/')}
          aria-label="SkyBrief home"
        >
          <Wind size={20} color="var(--color-brand)" strokeWidth={2.5} />
          <span className={shellStyles.wordmarkText}>SkyBrief</span>
        </button>

        {/* Stepper — hidden while on Skye page */}
        {!onSkyePage && (
          <nav className={shellStyles.stepper} aria-label="Progress steps">
            {STEPS.map((step, idx) => {
              const isCompleted = step.number < currentStep;
              const isActive    = step.number === currentStep;

              return (
                <div key={step.number} className={shellStyles.stepRow}>
                  {idx > 0 && (
                    <div
                      className={shellStyles.connector}
                      style={{
                        background: isCompleted
                          ? 'var(--color-brand)'
                          : 'var(--color-border)',
                      }}
                    />
                  )}

                  <div className={shellStyles.stepItem}>
                    <div
                      className={[
                        shellStyles.circle,
                        isActive    ? shellStyles.circleActive    : '',
                        isCompleted ? shellStyles.circleCompleted : '',
                        !isActive && !isCompleted ? shellStyles.circleFuture : '',
                      ].join(' ')}
                    >
                      {isCompleted ? (
                        <Check size={13} strokeWidth={3} />
                      ) : (
                        <span className={shellStyles.circleNum}>{step.number}</span>
                      )}
                    </div>

                    <span
                      className={[
                        isActive    ? shellStyles.stepLabelActive    : '',
                        isCompleted ? shellStyles.stepLabelCompleted : '',
                        !isActive && !isCompleted ? shellStyles.stepLabel : '',
                      ].join(' ')}
                    >
                      {step.label}
                    </span>
                  </div>
                </div>
              );
            })}
          </nav>
        )}

        {/* Persistent Skye tab */}
        <button
          className={[
            shellStyles.skyeTab,
            onSkyePage ? shellStyles.skyeTabActive : '',
          ].join(' ')}
          onClick={() => navigate('/chat')}
          aria-label="Ask Skye"
        >
          <Bot size={16} strokeWidth={2.5} />
          <span>Ask Skye</span>
        </button>
    </header>
  );

  if (headerOnly) return header;

  return (
    <div className={shellStyles.shell}>
      {header}
      <main className={shellStyles.main}>{children}</main>
    </div>
  );
}
