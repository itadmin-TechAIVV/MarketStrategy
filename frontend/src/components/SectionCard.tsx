import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type Provenance, type Section, type Source } from "../api";

interface Props {
  workspaceId: string;
  section: Section;
  sources: Map<string, Source>;
  disabled: boolean;
  onChanged: (s: Section) => void;
  onError: (msg: string) => void;
}

const PROV_LABEL: Record<Provenance, string> = { website: "Website", user: "You", assumption: "Assumption" };
const STATUS_LABEL = { draft: "Draft", confirmed: "Confirmed", needs_refresh: "Needs refresh" };

export default function SectionCard({ workspaceId, section, sources, disabled, onChanged, onError }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(section.body_md);
  const [showSources, setShowSources] = useState(false);
  const [saving, setSaving] = useState(false);

  const counts = section.claims.reduce<Record<string, number>>((acc, c) => {
    acc[c.provenance] = (acc[c.provenance] ?? 0) + 1;
    return acc;
  }, {});

  async function save() {
    setSaving(true);
    try {
      const res = await api.editSection(workspaceId, section.key, draft);
      onChanged(res.section);
      setEditing(false);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function confirm() {
    try {
      onChanged(await api.confirmSection(workspaceId, section.key));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not confirm");
    }
  }

  return (
    <article className={`section ${section.status}`}>
      <header className="section-head">
        <h3>{section.title}</h3>
        <div className="badges">
          <span className={`badge conf-${section.confidence.toLowerCase()}`}>{section.confidence} confidence</span>
          <span className={`badge status-${section.status}`}>{STATUS_LABEL[section.status]}</span>
          {section.user_edited && <span className="badge edited">Edited by you</span>}
        </div>
      </header>

      {section.status === "needs_refresh" && section.refresh_reason && (
        <div className="refresh-note">Needs refresh: {section.refresh_reason}. Ask the agent to update it, or confirm it as is.</div>
      )}

      {editing ? (
        <div className="edit-box no-print">
          <textarea rows={Math.min(18, Math.max(6, draft.split("\n").length + 1))} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="row">
            <button className="btn primary small" onClick={save} disabled={saving || !draft.trim()}>
              {saving ? "Saving…" : "Save as my version"}
            </button>
            <button
              className="btn ghost small"
              onClick={() => {
                setDraft(section.body_md);
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </div>
          <p className="muted small">Your text becomes the source of truth. Later sections that depend on it are flagged for refresh.</p>
        </div>
      ) : (
        <div className="section-body">
          <ReactMarkdown>{section.body_md}</ReactMarkdown>
        </div>
      )}

      <footer className="section-foot">
        <button className="link small" onClick={() => setShowSources((s) => !s)}>
          Sources:{" "}
          {(Object.keys(counts) as Provenance[]).map((p) => (
            <span key={p} className={`prov ${p}`}>
              {PROV_LABEL[p]} {counts[p]}
            </span>
          ))}
          {section.claims.length === 0 && <span className="muted">none</span>}
        </button>
        {!editing && (
          <div className="row no-print">
            <button
              className="btn ghost small"
              disabled={disabled}
              onClick={() => {
                setDraft(section.body_md);
                setEditing(true);
              }}
            >
              Edit
            </button>
            {section.status !== "confirmed" && (
              <button className="btn primary small" disabled={disabled} onClick={confirm}>
                Confirm
              </button>
            )}
          </div>
        )}
      </footer>

      {section.claims.length > 0 && (
        <ul className={`claims ${showSources ? "" : "print-only"}`}>
          {section.claims.map((c, i) => (
            <li key={i}>
              <span className={`prov ${c.provenance}`}>{PROV_LABEL[c.provenance]}</span> {c.text}
              {c.source_ids.map((sid) => {
                const s = sources.get(sid);
                if (!s) return null;
                return s.url ? (
                  <a key={sid} className="src-link" href={s.url} target="_blank" rel="noreferrer">
                    {s.title || s.url}
                  </a>
                ) : (
                  <span key={sid} className="src-link">
                    {s.title}
                  </span>
                );
              })}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
