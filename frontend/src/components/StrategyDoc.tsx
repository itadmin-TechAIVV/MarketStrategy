import type { Section, Source, WorkspaceDetail } from "../api";
import { api } from "../api";
import SectionCard from "./SectionCard";

interface Props {
  detail: WorkspaceDetail;
  sources: Source[];
  busy: boolean;
  onSectionChanged: (s: Section) => void;
  onError: (msg: string) => void;
}

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  confirmed: "Confirmed",
  needs_refresh: "Needs refresh",
};

export default function StrategyDoc({ detail, sources, busy, onSectionChanged, onError }: Props) {
  const byKey = new Map(detail.sections.map((s) => [s.key, s]));
  const sourceMap = new Map(sources.map((s) => [s.source_id, s]));
  const current = detail.workspace.current_stage;

  async function exportMd() {
    try {
      const md = await api.exportMarkdown(detail.workspace.id);
      const blob = new Blob([md], { type: "text/markdown" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${detail.workspace.product_name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-gtm-strategy.md`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Export failed");
    }
  }

  return (
    <section className="doc">
      <div className="doc-header">
        <div>
          <div className="eyebrow">GTM Strategy</div>
          <h1>{detail.workspace.product_name}</h1>
        </div>
        <div className="doc-actions no-print">
          <button className="btn ghost small" onClick={exportMd}>
            Export Markdown
          </button>
          <button className="btn ghost small" onClick={() => window.print()}>
            Print / PDF
          </button>
        </div>
      </div>

      <ol className="stage-rail no-print">
        {detail.stages.map((st) => (
          <li key={st.key} className={`stage-chip ${st.status} ${st.key === current ? "current" : ""} ${st.ready ? "" : "soon"}`}>
            <a href={`#stage-${st.key}`}>{st.title}</a>
            <span className="small">{st.ready ? STATUS_LABEL[st.status] : "Coming soon"}</span>
          </li>
        ))}
      </ol>

      <div className="legend no-print">
        <span className="prov website">Website</span>
        <span className="prov user">You</span>
        <span className="prov assumption">Assumption</span>
      </div>

      {detail.stages.map((st) => {
        const present = st.sections.filter((s) => byKey.has(s.key));
        const showEmpty = st.ready && (st.key === current || present.length > 0);
        if (!present.length && !showEmpty) {
          return (
            <div key={st.key} id={`stage-${st.key}`} className="stage-block collapsed">
              <h2>
                {st.title} <span className="muted small">{st.ready ? STATUS_LABEL[st.status] : "Coming in a later version"}</span>
              </h2>
            </div>
          );
        }
        return (
          <div key={st.key} id={`stage-${st.key}`} className="stage-block">
            <h2>
              {st.title} <span className={`status-tag ${st.status}`}>{STATUS_LABEL[st.status]}</span>
            </h2>
            {st.sections.map((def) => {
              const sec = byKey.get(def.key);
              if (!sec) {
                return (
                  <div key={def.key} className="section placeholder">
                    <h3>{def.title}</h3>
                    <p className="muted small">{busy ? "The agent is working on this…" : "Not written yet."}</p>
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
    </section>
  );
}
