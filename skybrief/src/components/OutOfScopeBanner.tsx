import { MapPin } from 'lucide-react';

export default function OutOfScopeBanner() {
  return (
    <div style={styles.banner}>
      <MapPin size={18} color="var(--color-danger)" strokeWidth={2.5} style={{ flexShrink: 0 }} />
      <p style={styles.text}>
        <strong style={styles.title}>Outside Service Area — </strong>
        SkyBrief currently covers California only. Please select a location within California.
      </p>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  banner: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    padding: '12px 14px',
    background: 'var(--color-danger-subtle)',
    border: '1px solid var(--color-danger)',
    borderRadius: 'var(--radius-md)',
    marginTop: '4px',
  },
  text: {
    margin: 0,
    fontSize: '13px',
    lineHeight: 1.5,
    color: 'var(--color-text-primary)',
  },
  title: {
    color: 'var(--color-danger)',
    fontWeight: 600,
  },
};
