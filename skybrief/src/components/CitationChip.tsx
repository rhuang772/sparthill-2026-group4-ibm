import { ExternalLink } from 'lucide-react';
import type { Citation } from '../types';
import styles from './CitationChip.module.css';

interface CitationChipProps {
  citation: Citation;
}

const LAYER_COLORS: Record<string, string> = {
  federal: '#3B82F6',
  'ca-state': '#D97706',
  local: '#BE185D',
};

export default function CitationChip({ citation }: CitationChipProps) {
  const dotColor = LAYER_COLORS[citation.layer] ?? '#94A3B8';

  return (
    <a
      href={citation.url}
      target="_blank"
      rel="noopener noreferrer"
      className={styles.chip}
    >
      <span
        className={styles.dot}
        style={{ background: dotColor }}
        aria-hidden="true"
      />
      <span className={styles.source}>{citation.source}</span>
      <ExternalLink size={11} className={styles.icon} />
    </a>
  );
}
