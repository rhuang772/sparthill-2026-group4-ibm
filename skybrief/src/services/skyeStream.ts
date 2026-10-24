/**
 * Client for the Skye streaming endpoints (/check/stream, /rules/stream).
 * The backend sends Server-Sent Events; see app/composer.py for the event types.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

export interface StreamTool {
  name: string;
  label: string;
  state: 'running' | 'done';
  status?: string;
}

export interface StreamHandlers<T> {
  onStatus?: (message: string) => void;
  onTool?: (tool: StreamTool) => void;
  onReset?: () => void;
  onToken: (text: string) => void;
  onDone: (response: T) => void;
}

/** GET an SSE endpoint and dispatch its events. Resolves when the stream ends. */
export async function streamSkye<T>(
  path: string,
  params: URLSearchParams,
  handlers: StreamHandlers<T>,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}?${params}`, {
    headers: { Accept: 'text/event-stream' },
    signal,
  });
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}${detail ? `: ${detail}` : ''}`);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  let finished = false;

  const dispatch = (block: string) => {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join('\n'));
    switch (event) {
      case 'status': handlers.onStatus?.(payload.message); break;
      case 'tool':   handlers.onTool?.(payload); break;
      case 'reset':  handlers.onReset?.(); break;
      case 'token':  handlers.onToken(payload.text); break;
      case 'done':   finished = true; handlers.onDone(payload as T); break;
      case 'error':  throw new Error(payload.message);
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, '\n');
    let sep: number;
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      dispatch(buffer.slice(0, sep));
      buffer = buffer.slice(sep + 2);
    }
  }
  if (buffer.trim()) dispatch(buffer);
  if (!finished) throw new Error('The stream ended before Skye finished answering');
}
