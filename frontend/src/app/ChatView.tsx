import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  api,
  streamChat,
  type AgentEvent,
  type AnswerMap,
  type Ask,
  type Section,
  type Source,
  type TranscriptItem,
  type WorkspaceDetail,
} from "../api";
import { IconMenu, IconPanel } from "../components/Icons";
import { useShell } from "./AppShell";
import Composer from "./Composer";
import StrategyPanel from "./StrategyPanel";
import Thread from "./Thread";

export interface LiveState {
  text: string;
  activity: string | null;
  crawl: string | null;
}

const EMPTY_LIVE: LiveState = { text: "", activity: null, crawl: null };
const wideScreen = () => typeof window !== "undefined" && window.innerWidth > 1100;

export default function ChatView() {
  const { id = "" } = useParams();
  const { refreshWorkspaces, openSidebar } = useShell();
  const [detail, setDetail] = useState<WorkspaceDetail | null>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [pendingAsk, setPendingAsk] = useState<Ask | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<LiveState>(EMPTY_LIVE);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [panelOpen, setPanelOpen] = useState(wideScreen);
  const kickedOff = useRef<string | null>(null);

  const refreshDetail = useCallback(async () => {
    const d = await api.workspace(id);
    setDetail(d);
    setPendingAsk(d.workspace.pending_ask);
    return d;
  }, [id]);
  const refreshSources = useCallback(() => api.sources(id).then(setSources), [id]);
  const refreshTranscript = useCallback(() => api.transcript(id).then(setTranscript), [id]);

  const upsertSection = (section: Section) =>
    setDetail((d) => (d ? { ...d, sections: [...d.sections.filter((s) => s.key !== section.key), section] } : d));

  const send = useCallback(
    async (body: { text?: string; answers?: AnswerMap }, optimistic: TranscriptItem | null) => {
      setError("");
      setBusy(true);
      setPendingAsk(null);
      setLive(EMPTY_LIVE);
      if (optimistic) setTranscript((t) => [...t, optimistic]);
      const onEvent = (e: AgentEvent) => {
        switch (e.type) {
          case "text":
            setLive((l) => ({ ...l, text: l.text + e.text, activity: null }));
            break;
          case "block_end":
            setLive((l) => (l.text && !l.text.endsWith("\n\n") ? { ...l, text: l.text + "\n\n" } : l));
            break;
          case "tool":
            setLive((l) => ({ ...l, activity: e.status === "start" ? e.label : null }));
            break;
          case "crawl":
            setLive((l) => ({
              ...l,
              crawl:
                e.status === "running"
                  ? `Reading your website · ${e.fetched ?? 0} pages${e.title ? ` · ${e.title}` : ""}`
                  : e.status === "failed"
                    ? null
                    : null,
            }));
            if (e.status === "failed" && e.error) setError(`Couldn't read the website: ${e.error}`);
            break;
          case "section":
            upsertSection(e.section);
            break;
          case "sections_changed":
          case "workspace_changed":
            void refreshDetail();
            break;
          case "sources_changed":
            void refreshSources();
            break;
          case "ask":
            setPendingAsk(e.ask);
            break;
          case "error":
            setError(e.message);
            break;
          case "done":
            break;
        }
      };
      try {
        await streamChat(id, body, onEvent);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Connection lost");
      } finally {
        await Promise.all([refreshTranscript(), refreshDetail(), refreshSources()]).catch(() => undefined);
        setLive(EMPTY_LIVE);
        setBusy(false);
        void refreshWorkspaces();
      }
    },
    [id, refreshDetail, refreshSources, refreshTranscript, refreshWorkspaces],
  );

  useEffect(() => {
    setLoaded(false);
    setDetail(null);
    setTranscript([]);
    setError("");
    Promise.all([refreshDetail(), refreshTranscript(), refreshSources()])
      .then(() => setLoaded(true))
      .catch((e) => setError(e.message));
  }, [refreshDetail, refreshTranscript, refreshSources]);

  // A brand-new strategy starts with the agent studying the website.
  useEffect(() => {
    if (!loaded || !detail || busy || kickedOff.current === id) return;
    if (transcript.length === 0 && !detail.workspace.busy) {
      kickedOff.current = id;
      const text = `Please study our website ${detail.workspace.website_url} and tell me what you understood about ${detail.workspace.product_name}.`;
      void send({ text }, { role: "user", kind: "text", text, seq: 0 });
    }
  }, [loaded, detail, transcript.length, busy, send, id]);

  const ready = detail?.stages.filter((s) => s.ready) ?? [];
  const totalSecs = ready.reduce((n, s) => n + s.sections.length, 0);
  const confirmed = detail?.sections.filter((s) => s.status === "confirmed" && ready.some((r) => r.key === s.stage)).length ?? 0;
  const pct = totalSecs ? Math.round((confirmed / totalSecs) * 100) : 0;
  const currentStage = detail?.stages.find((s) => s.key === detail.workspace.current_stage);

  return (
    <>
      <section className="conv">
        <header className="conv-header">
          <button className="icon-btn mobile-only" onClick={openSidebar} aria-label="Open menu">
            <IconMenu />
          </button>
          <div className="conv-title">
            <strong>{detail?.workspace.product_name ?? "Loading…"}</strong>
            {detail && (
              <a href={detail.workspace.website_url} target="_blank" rel="noreferrer">
                {detail.workspace.website_url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
              </a>
            )}
          </div>
          {detail && (
            <span className="progress-pill" title={`${confirmed} of ${totalSecs} sections confirmed`}>
              <span className="ring" style={{ ["--p" as string]: pct }} />
              <span className="progress-text">{currentStage?.title ?? "Strategy"} · {pct}%</span>
            </span>
          )}
          <button
            className={`icon-btn ${panelOpen ? "active" : ""}`}
            onClick={() => setPanelOpen((o) => !o)}
            title={panelOpen ? "Hide strategy" : "Show strategy"}
            aria-label="Toggle strategy document"
          >
            <IconPanel />
          </button>
        </header>

        <Thread
          transcript={transcript}
          live={live}
          busy={busy}
          error={error}
          pendingAsk={pendingAsk}
          onAnswer={(answers, summary) => send({ answers }, { role: "user", kind: "answer", text: summary, seq: Date.now() })}
        />

        <Composer
          workspaceId={id}
          busy={busy}
          placeholder={pendingAsk ? "Or answer in your own words…" : "Message the agent…"}
          onSend={(text) => send({ text }, { role: "user", kind: "text", text, seq: Date.now() })}
          onContextAdded={() => void refreshSources()}
        />
      </section>

      {panelOpen && detail && (
        <StrategyPanel
          detail={detail}
          sources={sources}
          busy={busy}
          onClose={() => setPanelOpen(false)}
          onSectionChanged={(s) => {
            upsertSection(s);
            void refreshDetail();
          }}
          onError={setError}
        />
      )}
    </>
  );
}
