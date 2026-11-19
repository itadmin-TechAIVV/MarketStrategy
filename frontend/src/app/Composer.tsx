import { useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { IconPaperclip, IconSend, IconX } from "../components/Icons";

interface Props {
  workspaceId: string;
  busy: boolean;
  placeholder: string;
  onSend: (text: string) => void;
  onContextAdded: () => void;
}

export default function Composer({ workspaceId, busy, placeholder, onSend, onContextAdded }: Props) {
  const [text, setText] = useState("");
  const [ctxOpen, setCtxOpen] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  function grow() {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const t = text.trim();
    if (!t || busy) return;
    setText("");
    requestAnimationFrame(grow);
    onSend(t);
  }

  return (
    <div className="composer-wrap no-print">
      {ctxOpen && (
        <ContextForm
          workspaceId={workspaceId}
          onClose={() => setCtxOpen(false)}
          onSaved={() => {
            setCtxOpen(false);
            onContextAdded();
          }}
        />
      )}
      <form className="composer" onSubmit={submit}>
        <textarea
          ref={ref}
          rows={1}
          placeholder={placeholder}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            grow();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          aria-label="Message"
        />
        <div className="composer-row">
          <div className="composer-tools">
            <button type="button" className={`btn ghost sm ${ctxOpen ? "active" : ""}`} onClick={() => setCtxOpen((o) => !o)}>
              <IconPaperclip size={16} /> Add context
            </button>
          </div>
          <button className="send-btn" disabled={busy || !text.trim()} aria-label="Send">
            <IconSend size={18} />
          </button>
        </div>
      </form>
      <div className="composer-hint">The agent only states what it can source. Check anything marked as an assumption.</div>
    </div>
  );
}

function ContextForm({ workspaceId, onClose, onSaved }: { workspaceId: string; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.addContext(workspaceId, title, body);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <form className="context-pop" onSubmit={save}>
      <div className="context-pop-head">
        <strong>Add context</strong>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          <IconX size={16} />
        </button>
      </div>
      <span className="muted small">Paste deck text, meeting notes or a competitor summary. The agent reads it on your next message.</span>
      <input className="input" required placeholder="Title, e.g. Sales deck Q3" value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea className="textarea" required rows={5} placeholder="Paste text here" value={body} onChange={(e) => setBody(e.target.value)} />
      {error && <div className="alert error">{error}</div>}
      <div>
        <button className="btn primary sm" disabled={saving}>
          {saving ? "Saving…" : "Save context"}
        </button>
      </div>
    </form>
  );
}
