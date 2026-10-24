import { useState } from 'react';
import { CheckCircle, XCircle } from 'lucide-react';
import type { QuizQuestion } from '../types';
import styles from './QuizQuestionCard.module.css';

interface QuizQuestionCardProps {
  question: QuizQuestion;
  questionNumber?: number;
  onAnswered?: (selectedIndex: number) => void;
  /** If provided, pre-select this answer (locked, read-only) */
  lockedIndex?: number;
}

export default function QuizQuestionCard({
  question,
  questionNumber,
  onAnswered,
  lockedIndex,
}: QuizQuestionCardProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(
    lockedIndex !== undefined ? lockedIndex : null,
  );
  const answered = selectedIndex !== null;

  function handleSelect(idx: number) {
    if (answered) return;
    setSelectedIndex(idx);
    onAnswered?.(idx);
  }

  function optionClass(idx: number): string {
    if (!answered) return styles.option;
    if (idx === question.correctIndex) return `${styles.option} ${styles.correct}`;
    if (idx === selectedIndex) return `${styles.option} ${styles.incorrect}`;
    return `${styles.option} ${styles.dimmed}`;
  }

  return (
    <div className={styles.card}>
      {questionNumber !== undefined && (
        <span className={styles.questionNumber}>Question {questionNumber}</span>
      )}
      <p className={styles.questionText}>{question.question}</p>

      <div className={styles.options}>
        {question.options.map((opt, idx) => (
          <button
            key={idx}
            className={optionClass(idx)}
            onClick={() => handleSelect(idx)}
            disabled={answered}
            aria-pressed={selectedIndex === idx}
          >
            <span className={styles.optionText}>{opt.text}</span>
            {answered && idx === question.correctIndex && (
              <CheckCircle size={16} strokeWidth={2} className={styles.iconCorrect} />
            )}
            {answered && idx === selectedIndex && idx !== question.correctIndex && (
              <XCircle size={16} strokeWidth={2} className={styles.iconIncorrect} />
            )}
          </button>
        ))}
      </div>

      {answered && (
        <div className={styles.explanation}>
          <span className={styles.explanationLabel}>
            {selectedIndex === question.correctIndex ? '✓ Correct' : '✗ Incorrect'}
          </span>
          {question.explanation}
        </div>
      )}
    </div>
  );
}
