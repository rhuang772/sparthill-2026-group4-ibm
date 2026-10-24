import { BookOpen, ExternalLink } from 'lucide-react';
import type { Lesson } from '../types';
import styles from './LessonCard.module.css';

interface LessonCardProps {
  lesson: Lesson;
}

export default function LessonCard({ lesson }: LessonCardProps) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <BookOpen size={20} color="var(--color-accent)" strokeWidth={2} />
        <h2 className={styles.title}>{lesson.title}</h2>
      </div>

      <blockquote className={styles.ruleText}>
        {lesson.ruleText}
      </blockquote>

      <div className={styles.context}>
        <p className={styles.contextLabel}>Why this matters for your flight</p>
        <p className={styles.contextText}>{lesson.context}</p>
      </div>

      <a
        href={lesson.citation.url}
        target="_blank"
        rel="noopener noreferrer"
        className={styles.citationBadge}
      >
        <ExternalLink size={12} strokeWidth={2} />
        <span>{lesson.citation.source}</span>
      </a>
    </div>
  );
}
