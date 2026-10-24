import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import type { Verdict } from '../types';
import styles from './VerdictCard.module.css';

interface VerdictCardProps {
  verdict: Verdict;
}

const verdictConfig = {
  go: {
    icon: CheckCircle,
    label: 'GO',
    // Shape tag text and symbol — readable without color
    shapeTag: '▲ Clear to fly',
    colorVar: 'var(--color-success)',
    className: styles.go,
    ariaLabel: 'Verdict: GO — clear to fly',
  },
  caution: {
    icon: AlertTriangle,
    label: 'CAUTION',
    shapeTag: '▲ Review before flying',
    colorVar: 'var(--color-caution)',
    className: styles.caution,
    ariaLabel: 'Verdict: CAUTION — review before flying',
  },
  'no-go': {
    icon: XCircle,
    label: 'NO-GO',
    shapeTag: '■ Do not fly',
    colorVar: 'var(--color-danger)',
    className: styles.noGo,
    ariaLabel: 'Verdict: NO-GO — do not fly',
  },
};

export default function VerdictCard({ verdict }: VerdictCardProps) {
  const config = verdictConfig[verdict.result];
  const Icon = config.icon;

  return (
    <div
      className={`${styles.card} ${config.className}`}
      role="status"
      aria-label={config.ariaLabel}
    >
      <div className={styles.header}>
        <Icon size={36} color={config.colorVar} strokeWidth={2.5} aria-hidden="true" />
        <span className={styles.label} style={{ color: config.colorVar }}>
          {config.label}
        </span>
        {/* Shape pill — verdict readable in grayscale / high contrast */}
        <span className={styles.shapePill} style={{ color: config.colorVar }}>
          {config.shapeTag}
        </span>
      </div>
      <p className={styles.summary}>{verdict.summary}</p>
    </div>
  );
}
