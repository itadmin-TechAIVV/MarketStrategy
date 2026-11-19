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
import ChatPane from "../components/ChatPane";
import StrategyDoc from "../components/StrategyDoc";
import TopBar from "../components/TopBar";

export interface LiveState {
  text: string;
  activity: string | null;
  crawl: string | null;
}

const EMPTY_LIVE: LiveState = { text: "", activity: null, crawl: null };

export default function WorkspacePage() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<WorkspaceDetail | null>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [pendingAsk, setPendingAsk] = useState<Ask | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<LiveState>(EMPTY_LIVE);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const kickedOff = useRef(false);

  const refreshDetail = useCallback(async () => {
    const d = await api.workspace(id);
    setDetail(d);
    setPendingAsk(d.workspace.pending_ask);
    return d;
  }, [id]);
  const refreshSources = useCallback(() => api.sources(id).then(setSources), [id]);
  const refreshTranscript = useCallback(() => api.transcript(id).then(setTranscript), [id]);

  const upsertSection = (section: Section) =>
    setDetail((d) => {
      if (!d) return d;
      const others = d.sections.filter((s) => s.key !== section.key);
      return { ...d, sections: [...others, section] };
    });

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
            setLive((l) => ({ ...l, activity: e.status === "start" ? `${e.label}…` : null }));
            break;
          case "crawl":
            setLive((l) => ({
              ...l,
              crawl:
                e.status === "running"
                  ? `Crawling: ${e.fetched ?? 0} pages${e.title ? ` · ${e.title}` : ""}`
                  : e.status === "failed"
                    ? `Crawl failed${e.error ? `: ${e.error}` : ""}`
                    : `Crawl finished: ${e.fetched ?? 0} pages stored`,
            }));
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
      }
    },
    [id, refreshDetail, refreshSources, refreshTranscript],
  );

  useEffect(() => {
    kickedOff.current = false;
    setLoaded(false);
    Promise.all([refreshDetail(), refreshTranscript(), refreshSources()])
      .then(() => setLoaded(true))
      .catch((e) => setError(e.message));
  }, [refreshDetail, refreshTranscript, refreshSources]);

  // A brand-new workspace starts with the agent studying the website.
  useEffect(() => {
    if (!loaded || !detail || kickedOff.current || busy) return;
    if (transcript.length === 0 && !detail.workspace.busy) {
      kickedOff.current = true;
      const text = `Please study our website ${detail.workspace.website_url} and tell me what you understood about ${detail.workspace.product_name}.`;
      void send({ text }, { role: "user", kind: "text", text, seq: 0 });
    }
  }, [loaded, detail, transcript.length, busy, send]);

  if (!detail) {
    return (
      <div className="page">
        <TopBar />
        <div className="center muted">{error || "Loading…"}</div>
      </div>
    );
  }

  return (
    <div className="page workspace-page">
      <TopBar>
        <strong>{detail.workspace.product_name}</strong>
        <a className="muted small" href={detail.workspace.website_url} target="_blank" rel="noreferrer">
          {detail.workspace.website_url}
        </a>
      </TopBar>
      <div className="split">
        <ChatPane
          workspaceId={id}
          transcript={transcript}
          live={live}
          busy={busy}
          error={error}
          pendingAsk={pendingAsk}
          onSendText={(text) => send({ text }, { role: "user", kind: "text", text, seq: Date.now() })}
          onAnswer={(answers, summary) => send({ answers }, { role: "user", kind: "answer", text: summary, seq: Date.now() })}
          onContextAdded={() => void refreshSources()}
        />
        <StrategyDoc
          detail={detail}
          sources={sources}
          busy={busy}
          onSectionChanged={(s) => {
            upsertSection(s);
            void refreshDetail();
          }}
          onError={setError}
        />
      </div>
    </div>
  );
}
