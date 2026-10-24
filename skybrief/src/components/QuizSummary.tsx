import { useNavigate } from 'react-router-dom';
import { GraduationCap, ArrowRight, CheckCircle, XCircle } from 'lucide-react';
import type { QuizQuestion } from '../types';
import styles from './QuizSummary.module.css';

interface QuizSummaryProps {
  score: number;
  total: number;
  preQuestion: QuizQuestion;
  preAnswerIndex: number;
}

export default function QuizSummary({
  score,
  total,
  preQuestion,
  preAnswerIndex,
}: QuizSummaryProps) {
  const navigate = useNavigate();
  const allCorrect = score === total;
  const preWasCorrect = preAnswerIndex === preQuestion.correctIndex;
  const preAnswerText = preQuestion.options[preAnswerIndex]?.text ?? '—';
  const correctAnswerText = preQuestion.options[preQuestion.correctIndex].text;

  return (
    <div className={styles.card}>
      {/* Score */}
      <div className={styles.scoreRow}>
        {allCorrect && (
          <span className={styles.graduationIcon} role="img" aria-label="Lesson complete">
            <GraduationCap size={28} strokeWidth={2} />
          </span>
        )}
        <div>
          <p className={styles.scoreLabel}>
            {allCorrect ? 'Lesson complete!' : 'Review complete'}
          </p>
          <p className={styles.scoreValue}>
            {score} / {total} correct
          </p>
        </div>
      </div>

      {/* Pre/post delta */}
      <div className={styles.deltaSection}>
        <p className={styles.deltaHeading}>Learning delta — Pre-flight check</p>
        <div className={styles.deltaRow}>
          <div className={styles.deltaItem}>
            <span className={styles.deltaLabel}>Before the lesson</span>
            <span className={`${styles.deltaAnswer} ${preWasCorrect ? styles.deltaCorrect : styles.deltaWrong}`}>
              {preWasCorrect ? (
                <CheckCircle size={14} strokeWidth={2} className={styles.deltaIcon} />
              ) : (
                <XCircle size={14} strokeWidth={2} className={styles.deltaIcon} />
              )}
              {preAnswerText}
            </span>
          </div>
          <div className={styles.deltaArrow}>→</div>
          <div className={styles.deltaItem}>
            <span className={styles.deltaLabel}>Correct answer</span>
            <span className={`${styles.deltaAnswer} ${styles.deltaCorrect}`}>
              <CheckCircle size={14} strokeWidth={2} className={styles.deltaIcon} />
              {correctAnswerText}
            </span>
          </div>
        </div>
        <p className={styles.deltaExplanation}>{preQuestion.explanation}</p>
      </div>

      {/* CTA */}
      <button className={styles.cta} onClick={() => navigate('/chat')}>
        Ask Skye a follow-up
        <ArrowRight size={16} strokeWidth={2} />
      </button>
    </div>
  );
}
