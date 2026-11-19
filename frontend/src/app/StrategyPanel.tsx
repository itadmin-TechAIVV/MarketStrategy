import { api, type Section, type Source, type WorkspaceDetail } from "../api";
import { IconCheck, IconDoc, IconDownload, IconPrinter, IconX } from "../components/Icons";
import SectionCard from "./SectionCard";

interface Props {
  detail: WorkspaceDetail;
  sources: Source[];
  busy: boolean;
  onClose: () => void;
  onSectionChanged: (s: Section) => void;
  onError: (msg: string) => void;
}

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  confirmed: "Confirmed",
  needs_refresh: "Needs refresh",
};
const STATUS_CHIP: Record<string, string> = { not_started: "gray", in_progress: "violet", confirmed: "green", needs_refresh: "amber" };

export default function StrategyPanel({ detail, sources, busy, onClose, onSectionChanged, onError }: Props) {
  const byKey = new Map(detail.sections.map((s) => [s.key, s]));
  const sourceMap = new Map(sources.map((s) => [s.source_id, s]));
  const current = detail.workspace.current_stage;
  const soon = detail.stages.filter((s) => !s.ready);

  async function exportMd() {
    try {
      const md = await api.exportMarkdown(detail.workspace.id);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
      a.download = `${detail.workspace.product_name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-gtm-strategy.md`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Export failed");
    }
  }

  return (
    <aside className="panel" aria-label="Strategy document">
      <div className="panel-head">
        <h2><IconDoc size={18} /> Strategy</h2>
        <button className="icon-btn" onClick={exportMd} title="Export Markdown" aria-label="Export Markdown"><IconDownload size={17} /></button>
        <button className="icon-btn" onClick={() => window.print()} title="Print or save as PDF" aria-label="Print or save as PDF"><IconPrinter size={17} /></button>
        <button className="icon-btn" onClick={onClose} title="Close" aria-label="Close strategy"><IconX size={17} /></button>
      </div>
      <div className="panel-scroll">
        <div className="doc-title">
          <span className="doc-eyebrow">GTM Strategy</span>
          <h1>{detail.workspace.product_name}</h1>
          <span className="muted small">
            {detail.workspace.website_url.replace(/^https?:\/\//, "").replace(/\/$/, "")} · {sources.length} source{sources.length === 1 ? "" : "s"}
          </span>
        </div>

        <nav className="stepper no-print" aria-label="Stages">
          {detail.stages.map((st, i) => (
            <a key={st.key} href={`#stage-${st.key}`} className={`${st.key === current ? "current" : ""} ${st.ready ? "" : "soon"}`}>
              <span className={`step-dot ${st.ready ? st.status : ""}`}>
                {st.status === "confirmed" ? <IconCheck size={12} strokeWidth={3} /> : i + 1}
              </span>
              <span>{st.title}</span>
              <span className="small muted">{st.ready ? STATUS_LABEL[st.status] : "Soon"}</span>
            </a>
          ))}
        </nav>

        <div className="legend no-print">
          Sources: <span className="prov website">Website</span><span className="prov user">You</span><span className="prov assumption">Assumption</span>
        </div>

        {detail.stages.filter((s) => s.ready).map((st) => {
          const present = st.sections.filter((s) => byKey.has(s.key));
          if (!present.length && st.key !== current) {
            return (
              <div key={st.key} id={`stage-${st.key}`} className="stage-block">
                <div className="stage-block-head">
                  <h2>{st.title}</h2>
                  <span className="chip gray">Not started</span>
                </div>
                <div className="stage-soon">Unlocks after the earlier stages are confirmed.</div>
              </div>
            );
          }
          return (
            <div key={st.key} id={`stage-${st.key}`} className="stage-block">
              <div className="stage-block-head">
                <h2>{st.title}</h2>
                <span className={`chip ${STATUS_CHIP[st.status]}`}><span className="dot" />{STATUS_LABEL[st.status]}</span>
              </div>
              {st.sections.map((def) => {
                const sec = byKey.get(def.key);
                if (!sec) {
                  return (
                    <div key={def.key} className="sec placeholder">
                      <div className="sec-head"><h3>{def.title}</h3></div>
                      <p className="muted small" style={{ marginTop: 4 }}>{busy ? "The agent is working on this…" : "Not written yet."}</p>
                    </div>
                  );
                }
                return (
                  <SectionCard
                    key={def.key}
                    workspaceId={detail.workspace.id}
                    section={sec}
                    sources={sourceMap}
                    disabled={busy}
                    onChanged={onSectionChanged}
                    onError={onError}
                  />
                );
              })}
            </div>
          );
        })}

        {soon.length > 0 && (
          <div className="stage-block no-print">
            <div className="stage-block-head">
              <h2>Coming next</h2>
            </div>
            {soon.map((st) => (
              <div key={st.key} id={`stage-${st.key}`} className="stage-soon">
                <span>{st.title}</span>
                <span className="chip gray">Coming soon</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
