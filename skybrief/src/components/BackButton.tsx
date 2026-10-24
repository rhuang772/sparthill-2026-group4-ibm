import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import styles from './BackButton.module.css';

interface BackButtonProps {
  to: string;
  label: string;
}

export default function BackButton({ to, label }: BackButtonProps) {
  const navigate = useNavigate();

  return (
    <button type="button" className={styles.backButton} onClick={() => navigate(to)}>
      <ArrowLeft size={16} strokeWidth={2.5} />
      {label}
    </button>
  );
}
