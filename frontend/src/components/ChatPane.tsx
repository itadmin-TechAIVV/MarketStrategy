import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { api, type AnswerMap, type Ask, type TranscriptItem } from "../api";
import type { LiveState } from "../pages/WorkspacePage";
import AskCard from "./AskCard";

interface Props {
  workspaceId: string;
  transcript: TranscriptItem[];
  live: LiveState;
  busy: boolean;
  error: string;
  pendingAsk: Ask | null;
  onSendText: (text: string) => void;
  onAnswer: (answers: AnswerMap, summary: string) => void;
  onContextAdded: () => void;
}

export default function ChatPane(p: Props) {
  const [text, setText] = useState("");
  const [showContext, setShowContext] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [p.transcript.length, p.live.text, p.pendingAsk, p.live.activity]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const t = text.trim();
    if (!t || p.busy) return;
    setText("");
    p.onSendText(t);
  }

  // The latest ask is answered via the pending card; earlier asks are shown collapsed.
  const lastAskSeq = [...p.transcript].reverse().find((i) => i.kind === "ask")?.seq;

  return (
    <section className="chat no-print">
      <div className="chat-scroll">
        {p.transcript.map((item, i) => {
          if (item.kind === "ask" && item.ask) {
            if (p.pendingAsk && item.seq === lastAskSeq) return null;
            return (
              <div key={i} className="msg assistant ask-past">
                {item.ask.intro && <ReactMarkdown>{item.ask.intro}</ReactMarkdown>}
                <ul>
                  {item.ask.questions.map((q) => (
                    <li key={q.id}>
                      <ReactMarkdown>{q.text}</ReactMarkdown>
                    </li>
                  ))}
                </ul>
              </div>
            );
          }
          return (
            <div key={i} className={`msg ${item.role} ${item.kind === "answer" ? "answer" : ""}`}>
              <ReactMarkdown>{item.text ?? ""}</ReactMarkdown>
            </div>
          );
        })}
        {p.live.text && (
          <div className="msg assistant">
            <ReactMarkdown>{p.live.text}</ReactMarkdown>
          </div>
        )}
        {p.busy && (
          <div className="activity">
            <span className="dot-pulse" /> {p.live.crawl ?? p.live.activity ?? "Thinking…"}
          </div>
        )}
        {p.pendingAsk && !p.busy && <AskCard ask={p.pendingAsk} onSubmit={p.onAnswer} />}
        {p.error && <div className="error">{p.error}</div>}
        <div ref={endRef} />
      </div>

      {showContext && (
        <ContextForm
          workspaceId={p.workspaceId}
          onDone={() => {
            setShowContext(false);
            p.onContextAdded();
          }}
        />
      )}

      <form className="composer" onSubmit={submit}>
        <textarea
          rows={2}
          placeholder={p.pendingAsk ? "Or answer in your own words…" : "Message the agent…"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) submit(e);
          }}
          disabled={p.busy}
        />
        <div className="composer-actions">
          <button type="button" className="btn ghost small" onClick={() => setShowContext((s) => !s)}>
            + Add context
          </button>
          <button className="btn primary" disabled={p.busy || !text.trim()}>
            Send
          </button>
        </div>
      </form>
    </section>
  );
}

function ContextForm({ workspaceId, onDone }: { workspaceId: string; onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.addContext(workspaceId, title, body);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <form className="context-form card" onSubmit={save}>
      <strong>Add context</strong>
      <span className="muted small">Paste deck text, notes or a competitor summary. The agent reads it on your next message.</span>
      <input required placeholder="Title (e.g. Sales deck Q3)" value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea required rows={5} placeholder="Paste text here" value={body} onChange={(e) => setBody(e.target.value)} />
      {error && <div className="error">{error}</div>}
      <button className="btn primary small" disabled={saving}>
        {saving ? "Saving…" : "Save context"}
      </button>
    </form>
  );
}
