import { AlertTriangle } from 'lucide-react';
import styles from './NotReadyBanner.module.css';

export default function NotReadyBanner() {
  return (
    <div className={styles.banner} role="alert">
      <AlertTriangle size={20} className={styles.icon} aria-hidden="true" />
      <div className={styles.body}>
        <p className={styles.title}>You're not ready to fly yet.</p>
        <p className={styles.message}>
          Recreational pilots must pass the free TRUST test before flying.{' '}
          <a
            href="https://www.faa.gov/uas/recreational_fliers/knowledge_test_updates"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.link}
          >
            Take the free TRUST test →
          </a>
        </p>
      </div>
    </div>
  );
}
