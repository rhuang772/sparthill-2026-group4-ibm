import type { ChatMessage } from '../types';
import CitationChip from './CitationChip';
import styles from './ChatBubble.module.css';

interface ChatBubbleProps {
  message: ChatMessage;
}

export default function ChatBubble({ message }: ChatBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={isUser ? styles.rowUser : styles.rowSkye}>
      <div className={isUser ? styles.bubbleUser : styles.bubbleSkye}>
        <p className={styles.text}>{message.text}</p>
        {!isUser && message.citation && (
          <div className={styles.citationRow}>
            <CitationChip citation={message.citation} />
          </div>
        )}
      </div>
    </div>
  );
}
