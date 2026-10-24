import { Wind, Sun, Droplets, Users, Plane } from 'lucide-react';
import type { RiskFactor } from '../types';
import styles from './RiskFactorCard.module.css';

interface RiskFactorCardProps {
  factor: RiskFactor;
}

const ICON_MAP: Record<string, React.ComponentType<{ size: number; color: string; strokeWidth: number }>> = {
  wind: Wind,
  light: Sun,
  water: Droplets,
  crowds: Users,
  airspace: Plane,
};

const SEVERITY_COLOR: Record<RiskFactor['severity'], string> = {
  low: 'var(--color-success)',
  medium: 'var(--color-caution)',
  high: 'var(--color-danger)',
};

const SEVERITY_CLASS: Record<RiskFactor['severity'], string> = {
  low: styles.low,
  medium: styles.medium,
  high: styles.high,
};

export default function RiskFactorCard({ factor }: RiskFactorCardProps) {
  const Icon = ICON_MAP[factor.type] ?? Wind;
  const color = SEVERITY_COLOR[factor.severity];
  const severityClass = SEVERITY_CLASS[factor.severity];

  return (
    <div className={`${styles.card} ${severityClass}`}>
      <div className={styles.iconWrap}>
        <Icon size={22} color={color} strokeWidth={2} />
      </div>
      <div className={styles.body}>
        <span className={styles.label} style={{ color }}>{factor.label}</span>
        <p className={styles.detail}>{factor.detail}</p>
      </div>
    </div>
  );
}
