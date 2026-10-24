import { MapPin } from 'lucide-react';
import type { AlternativeLocation } from '../types';
import styles from './AlternativeSuggestion.module.css';

interface AlternativeSuggestionProps {
  alternative: AlternativeLocation;
}

export default function AlternativeSuggestion({ alternative }: AlternativeSuggestionProps) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <MapPin size={20} color="var(--color-accent)" strokeWidth={2} />
        <div className={styles.titleRow}>
          <span className={styles.name}>{alternative.name}</span>
          <span className={styles.distanceBadge}>{alternative.distance}</span>
        </div>
      </div>
      <p className={styles.reason}>{alternative.reason}</p>
      <p className={styles.footnote}>
        Suggested by SkyBrief data engine — not AI-generated
      </p>
    </div>
  );
}
