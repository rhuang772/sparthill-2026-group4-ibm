import type { ChatMessage } from '../types';
import CitationChip from './CitationChip';
import styles from './ChatBubble.module.css';

interface ChatBubbleProps {
  message: ChatMessage;
  /** Show a typing caret while the reply is still arriving. */
  streaming?: boolean;
}

export default function ChatBubble({ message, streaming = false }: ChatBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={isUser ? styles.rowUser : styles.rowSkye}>
      <div className={isUser ? styles.bubbleUser : styles.bubbleSkye}>
        <p className={styles.text}>
          {message.text}
          {streaming && <span className={styles.caret} aria-hidden="true" />}
        </p>
        {!isUser && message.citation && (
          <div className={styles.citationRow}>
            <CitationChip citation={message.citation} />
          </div>
        )}
      </div>
    </div>
  );
}
