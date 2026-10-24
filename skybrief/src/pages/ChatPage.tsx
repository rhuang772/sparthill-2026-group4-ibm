import { useRef, useState, useEffect } from 'react';
import { Bot, Send, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import ChatBubble from '../components/ChatBubble';
import type { ChatMessage } from '../types';
import styles from './ChatPage.module.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

interface RulesResponse {
  answer_markdown: string;
  citations: Array<{ rule_id: string; citation: string; source_url: string; dummy: boolean }>;
  mock_data: boolean;
}

/** Strip markdown syntax to plain text for the chat bubble. */
function stripMarkdown(md: string): string {
  return md
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^---+$/gm, '')
    .replace(/^[-*]\s/gm, '• ')
    .trim();
}

const GREETING: ChatMessage = {
  role: 'skye',
  text: "Hi! I'm Skye, your drone flight coach. I can answer questions about FAA rules, airspace, registration, TFRs, LAANC, and anything else related to safe recreational drone flight. What would you like to know?",
};

const SUGGESTED_PROMPTS = [
  'What is a TFR?',
  'Do I need to register my drone?',
  'What is LAANC?',
  'Can I fly in controlled airspace?',
];

export default function ChatPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [inputValue, setInputValue] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [sessionId] = useState(() => `chat-${Date.now()}`);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return;

    const userMsg: ChatMessage = { role: 'user', text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setIsThinking(true);

    try {
      const params = new URLSearchParams({ query: trimmed, session_id: sessionId });
      const res = await fetch(`${API_BASE}/rules?${params}`);
      if (!res.ok) {
        const detail = await res.text().catch(() => `HTTP ${res.status}`);
        throw new Error(`API error ${res.status}: ${detail}`);
      }
      const data: RulesResponse = await res.json();
      const plain = stripMarkdown(data.answer_markdown);
      const skyeMsg: ChatMessage = {
        role: 'skye',
        text: plain + (data.mock_data ? '\n\n⚠ Demo rules corpus was used.' : ''),
      };
      setMessages((prev) => [...prev, skyeMsg]);
    } catch (err) {
      const errMsg: ChatMessage = {
        role: 'skye',
        text:
          `Could not reach the Skye API (${String(err)}). ` +
          'Make sure the backend is running: make run',
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsThinking(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(inputValue);
  }

  return (
    // AppShell with currentStep=0 — stepper is hidden, Skye tab shows active state
    <AppShell currentStep={0}>
      <div className={styles.page}>

        {/* ── Skye header ── */}
        <div className={styles.chatHeader}>
          <button
            className={styles.backButton}
            onClick={() => navigate(-1)}
            aria-label="Go back"
          >
            <ArrowLeft size={16} strokeWidth={2.5} />
            Back
          </button>

          <div className={styles.headerCenter}>
            <div className={styles.avatarCircle}>
              <Bot size={20} color="#fff" strokeWidth={2.5} />
            </div>
            <div className={styles.headerInfo}>
              <span className={styles.skyeName}>Skye</span>
              <div className={styles.subtitleRow}>
                <span className={styles.subtitle}>AI Flight Coach</span>
                <span className={styles.groundedBadge}>Official sources only</span>
              </div>
            </div>
          </div>

          {/* spacer to balance the back button */}
          <div className={styles.headerSpacer} />
        </div>

        {/* ── Message list ── */}
        <div className={styles.messageList}>
          {messages.map((msg, i) => (
            <ChatBubble key={i} message={msg} />
          ))}

          {isThinking && (
            <div className={styles.thinkingRow}>
              <div className={styles.thinkingBubble}>
                <span className={styles.dot} />
                <span className={styles.dot} />
                <span className={styles.dot} />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* ── Input area ── */}
        <div className={styles.inputArea}>
          <div className={styles.suggestedRow}>
            {SUGGESTED_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                className={styles.suggestedChip}
                onClick={() => sendMessage(prompt)}
                disabled={isThinking}
                type="button"
              >
                {prompt}
              </button>
            ))}
          </div>

          <form className={styles.inputForm} onSubmit={handleSubmit}>
            <input
              className={styles.textInput}
              type="text"
              placeholder="Ask Skye about flight regulations, airspace, rules…"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              disabled={isThinking}
              autoComplete="off"
            />
            <button
              type="submit"
              className={styles.sendButton}
              disabled={!inputValue.trim() || isThinking}
              aria-label="Send"
            >
              <Send size={16} strokeWidth={2.5} />
            </button>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
