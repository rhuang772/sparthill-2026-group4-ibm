import { useState } from 'react';
import { CheckCircle, AlertTriangle, XCircle, ChevronDown, ChevronUp } from 'lucide-react';
import type { RuleFinding, RuleLayer } from '../types';
import styles from './RulesAccordion.module.css';

interface RulesAccordionProps {
  findings: RuleFinding[];
}

type LayerMeta = {
  label: string;
  colorVar: string;
  className: string;
};

const LAYER_META: Record<RuleLayer, LayerMeta> = {
  federal: {
    label: 'Federal',
    colorVar: 'var(--color-federal)',
    className: styles.badgeFederal,
  },
  'ca-state': {
    label: 'CA State',
    colorVar: 'var(--color-ca-state)',
    className: styles.badgeCaState,
  },
  local: {
    label: 'Local',
    colorVar: 'var(--color-local)',
    className: styles.badgeLocal,
  },
};

const LAYER_ORDER: RuleLayer[] = ['federal', 'ca-state', 'local'];

function StatusIcon({ status }: { status: RuleFinding['status'] }) {
  if (status === 'pass') return <CheckCircle size={18} color="var(--color-success)" strokeWidth={2} />;
  if (status === 'warn') return <AlertTriangle size={18} color="var(--color-caution)" strokeWidth={2} />;
  return <XCircle size={18} color="var(--color-danger)" strokeWidth={2} />;
}

function LayerSection({ layer, findings }: { layer: RuleLayer; findings: RuleFinding[] }) {
  const [open, setOpen] = useState(true);
  const meta = LAYER_META[layer];

  return (
    <div className={styles.section}>
      <button
        className={styles.sectionHeader}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className={styles.headerLeft}>
          <span className={`${styles.badge} ${meta.className}`}>{meta.label}</span>
          <span className={styles.count}>
            {findings.length} finding{findings.length !== 1 ? 's' : ''}
          </span>
        </div>
        {open ? (
          <ChevronUp size={16} color="var(--color-text-secondary)" />
        ) : (
          <ChevronDown size={16} color="var(--color-text-secondary)" />
        )}
      </button>

      {open && (
        <ul className={styles.findingList}>
          {findings.map((finding, idx) => (
            <li key={idx} className={styles.findingItem}>
              <div className={styles.findingIcon}>
                <StatusIcon status={finding.status} />
              </div>
              <div className={styles.findingBody}>
                <span className={styles.findingTitleRow}>
                  <span className={styles.findingTitle}>{finding.title}</span>
                  {finding.mocked && (
                    <span className={styles.mockedBadge} title="Simulated data — not a live feed">
                      Mocked
                    </span>
                  )}
                </span>
                <p className={styles.findingExplanation}>{finding.explanation}</p>
                <a
                  href={finding.citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.citation}
                >
                  {finding.citation.source} ↗
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function RulesAccordion({ findings }: RulesAccordionProps) {
  const byLayer = LAYER_ORDER.reduce<Record<RuleLayer, RuleFinding[]>>(
    (acc, layer) => {
      acc[layer] = findings.filter((f) => f.layer === layer);
      return acc;
    },
    { federal: [], 'ca-state': [], local: [] },
  );

  return (
    <div className={styles.accordion}>
      {LAYER_ORDER.filter((layer) => byLayer[layer].length > 0).map((layer) => (
        <LayerSection key={layer} layer={layer} findings={byLayer[layer]} />
      ))}
    </div>
  );
}
