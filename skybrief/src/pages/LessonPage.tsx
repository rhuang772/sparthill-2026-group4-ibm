import { useState } from 'react';
import AppShell from '../components/AppShell';
import BackButton from '../components/BackButton';
import LessonCard from '../components/LessonCard';
import QuizQuestionCard from '../components/QuizQuestionCard';
import QuizSummary from '../components/QuizSummary';
import { mockLesson, preQuestion, quizQuestions } from '../data/mockLesson';
import styles from './LessonPage.module.css';

export default function LessonPage() {
  // pre-question state
  const [preAnswerIndex, setPreAnswerIndex] = useState<number | null>(null);

  // quiz answers: null = not yet answered, number = selected index
  const [quizAnswers, setQuizAnswers] = useState<(number | null)[]>(
    quizQuestions.map(() => null),
  );

  const preAnswered = preAnswerIndex !== null;
  const allQuizAnswered = quizAnswers.every((a) => a !== null);
  const showSummary = preAnswered && allQuizAnswered;

  const score = quizAnswers.reduce<number>((acc, ans, idx) => {
    if (ans === quizQuestions[idx].correctIndex) return acc + 1;
    return acc;
  }, 0);

  function handleQuizAnswer(questionIdx: number, selectedIdx: number) {
    setQuizAnswers((prev) => {
      const next = [...prev];
      next[questionIdx] = selectedIdx;
      return next;
    });
  }

  return (
    <AppShell currentStep={4}>
      <div className={styles.page}>
        <div className={styles.container}>
          <BackButton to="/briefing" label="Back to Briefing" />

          {/* ── Section header ───────────────────────────────────────── */}
          <div className={styles.sectionHeader}>
            <h1 className={styles.pageTitle}>Rules Lesson</h1>
            <p className={styles.pageSubtitle}>
              Based on your Coyote Lake flight plan briefing
            </p>
          </div>

          {/* ── Pre-flight check ────────────────────────────────────── */}
          <section className={styles.section}>
            <div className={styles.sectionLabel}>
              <span className={styles.sectionBadge}>Pre-Flight Check</span>
              <p className={styles.sectionHint}>
                Answer before reading the lesson to see how your knowledge changes.
              </p>
            </div>
            <QuizQuestionCard
              question={preQuestion}
              onAnswered={(idx) => setPreAnswerIndex(idx)}
            />
          </section>

          {/* ── Lesson card (revealed after pre-question answered) ───── */}
          {preAnswered && (
            <section className={styles.section}>
              <div className={styles.sectionLabel}>
                <span className={styles.sectionBadge}>Lesson</span>
              </div>
              <LessonCard lesson={mockLesson} />
            </section>
          )}

          {/* ── Quiz questions ───────────────────────────────────────── */}
          {preAnswered && (
            <section className={styles.section}>
              <div className={styles.sectionLabel}>
                <span className={styles.sectionBadge}>Knowledge Check</span>
                <p className={styles.sectionHint}>
                  {allQuizAnswered
                    ? 'Quiz complete — see your results below.'
                    : `Answer all ${quizQuestions.length} questions to complete the lesson.`}
                </p>
              </div>
              <div className={styles.quizStack}>
                {quizQuestions.map((q, idx) => (
                  <QuizQuestionCard
                    key={idx}
                    question={q}
                    questionNumber={idx + 1}
                    onAnswered={(selected) => handleQuizAnswer(idx, selected)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* ── Summary (after all quiz questions answered) ──────────── */}
          {showSummary && (
            <section className={styles.section}>
              <div className={styles.sectionLabel}>
                <span className={styles.sectionBadge}>Results</span>
              </div>
              <QuizSummary
                score={score}
                total={quizQuestions.length}
                preQuestion={preQuestion}
                preAnswerIndex={preAnswerIndex!}
              />
            </section>
          )}
        </div>
      </div>
    </AppShell>
  );
}
