import { useRef, useState, useEffect } from 'react';
import { Bot, Send, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppShell from '../components/AppShell';
import ChatBubble from '../components/ChatBubble';
import { getSkyeResponse } from '../data/mockSkye';
import type { ChatMessage } from '../types';
import styles from './ChatPage.module.css';

const GREETING: ChatMessage = {
  role: 'skye',
  text: "Hi! I'm Skye, your SkyBrief flight coach. I can answer questions about FAA rules, California drone laws, airspace, registration, TFRs, and anything else related to safe recreational drone flight. What would you like to know?",
  citation: {
    source: 'FAA UAS Resource Hub',
    url: 'https://www.faa.gov/uas',
    layer: 'federal',
  },
};

const SUGGESTED_PROMPTS = [
  'What is a TFR?',
  'Do I need to register my drone?',
  'Can I fly after sunset?',
  'What is LAANC?',
];

export default function ChatPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [inputValue, setInputValue] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return;

    const userMsg: ChatMessage = { role: 'user', text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setIsThinking(true);

    setTimeout(() => {
      const skyeResp = getSkyeResponse(trimmed);
      const skyeMsg: ChatMessage = {
        role: 'skye',
        text: skyeResp.text,
        citation: skyeResp.citation,
      };
      setMessages((prev) => [...prev, skyeMsg]);
      setIsThinking(false);
    }, 400);
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
