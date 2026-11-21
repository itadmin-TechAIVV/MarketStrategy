import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type JackMessage, type Workspace } from "../../api";
import { useAuth } from "../../auth";
import { IconArrowRight, IconCheck, IconSend, IconX } from "../../components/Icons";
import JackAvatar from "../../components/JackAvatar";
import type { SettingsTab } from "../settings/SettingsDialog";

interface Props {
  workspaces: Workspace[] | null;
  onClose: () => void;
  onOpenSettings: (tab: SettingsTab) => void;
}

/** One tip per onboarding day, so a returning user learns something new each time Jack says hello. */
const DAY_TIPS = [
  "Start by pasting your product's website. I'll read it and write a brief you can check, section by section.",
  "Every claim in your strategy shows where it came from: the website, you, or an assumption. Open **Sources** under a section to check.",
  "Something not quite right? Press **Edit** on a section. Your version wins, and later stages are flagged for a refresh.",
  "Got call notes or a pitch deck summary? Add it with the **paperclip** in the message box and the agent will use it.",
  "The ICP stage asks a few multiple-choice questions. The first option is the agent's suggestion, but your answer decides.",
  "You can export a strategy as **Markdown**, or print it as a PDF, from the icons on the strategy panel.",
  "Prefer softer colours? Try the **Warm** theme in Settings → Appearance.",
  "You can leave in the middle of a question. The agent remembers where you stopped.",
  "Use the search box in the left panel to jump between strategies quickly.",
  "Last day of getting started! I'm still here afterwards: open me from the left panel any time.",
];

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function JackPanel({ workspaces, onClose, onOpenSettings }: Props) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [messages, setMessages] = useState<JackMessage[] | null>(null);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.jackMessages().then(setMessages).catch(() => setMessages([]));
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    // Esc closes the top layer only: a dialog or menu opened over Jack handles it first.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector(".modal-backdrop, .user-menu")) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  if (!user) return null;
  const first = user.name.split(" ")[0];
  const ob = user.onboarding;
  const list = workspaces ?? [];
  const strategyId = location.pathname.match(/^\/app\/w\/([^/]+)/)?.[1] ?? null;
  const tip = ob?.active ? DAY_TIPS[Math.min(ob.day, DAY_TIPS.length) - 1] : null;

  const checklist = [
    { label: "Start your first strategy", done: list.length > 0 },
    { label: "Confirm the brief", done: list.some((w) => w.current_stage !== "brief") },
    { label: "Finish the ICP", done: list.some((w) => !["brief", "icp"].includes(w.current_stage)) },
    { label: "Set your own password", done: Boolean(user.password_changed_at) },
  ];
  const doneCount = checklist.filter((c) => c.done).length;

  const latest = list[0];
  const starters =
    list.length === 0
      ? ["How do I start a strategy?", "What will the agent do?", "How are claims sourced?"]
      : [`What's next for ${latest.product_name}?`, "How do I edit a section?", "How do I export my strategy?"];
  const lastJack = [...(messages ?? [])].reverse().find((m) => m.role === "jack");
  const chips = thinking ? [] : lastJack ? lastJack.suggestions : starters;

  async function send(question: string) {
    const q = question.trim();
    if (!q || thinking) return;
    setError("");
    setText("");
    const temp: JackMessage = {
      id: `tmp-${Date.now()}`, role: "user", text: q, suggestions: [], action: "none",
      strategy_id: "", action_label: "", created_at: new Date().toISOString(),
    };
    setMessages((m) => [...(m ?? []), temp]);
    setThinking(true);
    try {
      const res = await api.askJack(q, { path: location.pathname, strategy_id: strategyId });
      setMessages((m) => [...(m ?? []).filter((x) => x.id !== temp.id), res.user, res.jack]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Jack couldn't answer right now.");
      setText(q);
      setMessages((m) => (m ?? []).filter((x) => x.id !== temp.id));
    } finally {
      setThinking(false);
      inputRef.current?.focus();
    }
  }

  function runAction(m: JackMessage) {
    if (m.action === "new_strategy") navigate("/app");
    else if (m.action === "open_strategy" && m.strategy_id) navigate(`/app/w/${m.strategy_id}`);
    else if (m.action === "open_settings") onOpenSettings("profile");
    else if (m.action === "open_security") onOpenSettings("security");
    if (window.innerWidth < 860) onClose();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(text);
  }

  return (
    <aside className="jack-panel" role="dialog" aria-label="Jack, your guide">
      <header className="jack-head">
        <JackAvatar size={34} />
        <div className="jack-title">
          <strong>Jack</strong>
          <span><i className="live-dot" /> Your guide{ob?.active ? ` · Day ${ob.day} of ${ob.total_days}` : ""}</span>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close Jack" title="Close (Esc)">
          <IconX size={18} />
        </button>
      </header>

      <div className="jack-scroll" ref={scrollRef}>
        <div className="jack-msg jack">
          <JackAvatar size={26} wave />
          <div className="jack-bubble">
            <p className="jack-hello">{greeting()}, {first}! 👋</p>
            <p>How can I help you today?</p>
            {tip && (
              <div className="jack-tip">
                <span>Tip for day {ob!.day}</span>
                <ReactMarkdown>{tip}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>

        {ob?.active && (
          <div className="jack-checklist">
            <div className="jack-checklist-head">
              <strong>Getting started</strong>
              <span>{doneCount} of {checklist.length}</span>
            </div>
            <div className="jack-progress"><i style={{ width: `${(doneCount / checklist.length) * 100}%` }} /></div>
            <ul>
              {checklist.map((c) => (
                <li key={c.label} className={c.done ? "done" : ""}>
                  <span className="jack-check">{c.done && <IconCheck size={11} strokeWidth={3} />}</span>
                  {c.label}
                </li>
              ))}
            </ul>
          </div>
        )}

        {messages === null && <div className="jack-loading"><span className="spinner" /></div>}

        {(messages ?? []).map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="jack-msg user"><div className="jack-bubble">{m.text}</div></div>
          ) : (
            <div key={m.id} className="jack-msg jack">
              <JackAvatar size={26} />
              <div className="jack-bubble md">
                <ReactMarkdown>{m.text}</ReactMarkdown>
                {m.action !== "none" && (
                  <button className="btn tonal sm jack-action" onClick={() => runAction(m)}>
                    {m.action_label} <IconArrowRight size={14} />
                  </button>
                )}
              </div>
            </div>
          ),
        )}

        {thinking && (
          <div className="jack-msg jack">
            <JackAvatar size={26} />
            <div className="jack-bubble"><span className="typing"><i /><i /><i /></span></div>
          </div>
        )}
        {error && <div className="alert error">{error}</div>}
      </div>

      {chips.length > 0 && (
        <div className="jack-chips">
          {chips.map((c) => (
            <button key={c} onClick={() => void send(c)}>{c}</button>
          ))}
        </div>
      )}

      <form className="jack-composer" onSubmit={submit}>
        <textarea
          ref={inputRef}
          rows={1}
          placeholder="Ask Jack anything…"
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(text);
            }
          }}
          aria-label="Message Jack"
        />
        <button className="send-btn" disabled={!text.trim() || thinking} aria-label="Send">
          <IconSend size={17} />
        </button>
      </form>
    </aside>
  );
}
