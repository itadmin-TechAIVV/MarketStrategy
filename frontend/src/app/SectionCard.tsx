import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type Provenance, type Section, type Source } from "../api";
import { IconCheck, IconChevron, IconEdit, IconLink, IconRefresh } from "../components/Icons";

interface Props {
  workspaceId: string;
  section: Section;
  sources: Map<string, Source>;
  disabled: boolean;
  onChanged: (s: Section) => void;
  onError: (msg: string) => void;
}

const PROV_LABEL: Record<Provenance, string> = { website: "Website", user: "You", assumption: "Assumption" };
const STATUS = {
  draft: { label: "Draft", chip: "violet" },
  confirmed: { label: "Confirmed", chip: "green" },
  needs_refresh: { label: "Needs refresh", chip: "amber" },
} as const;
const CONF_CHIP = { High: "green", Medium: "amber", Low: "red" } as const;

export default function SectionCard({ workspaceId, section, sources, disabled, onChanged, onError }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(section.body_md);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const counts = section.claims.reduce<Partial<Record<Provenance, number>>>((acc, c) => {
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
    <article className={`sec ${section.status}`}>
      <header className="sec-head">
        <h3>{section.title}</h3>
        <div className="sec-badges">
          <span className={`chip ${CONF_CHIP[section.confidence]}`} title="Confidence">{section.confidence}</span>
          <span className={`chip ${STATUS[section.status].chip}`}>{STATUS[section.status].label}</span>
          {section.user_edited && <span className="chip blue">Your version</span>}
        </div>
      </header>

      {section.status === "needs_refresh" && section.refresh_reason && (
        <div className="refresh-note"><IconRefresh size={14} /> {section.refresh_reason}. Ask the agent to update it, or confirm it as is.</div>
      )}

      {editing ? (
        <div className="edit-box no-print">
          <textarea className="textarea" rows={Math.min(16, Math.max(5, draft.split("\n").length + 1))} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn primary sm" onClick={save} disabled={saving || !draft.trim()}>
              {saving ? "Saving…" : "Save my version"}
            </button>
            <button className="btn ghost sm" onClick={() => { setDraft(section.body_md); setEditing(false); }}>Cancel</button>
          </div>
          <p className="muted small">Your text becomes the source of truth. Sections that depend on it are flagged for refresh.</p>
        </div>
      ) : (
        <div className="sec-body md"><ReactMarkdown>{section.body_md}</ReactMarkdown></div>
      )}

      <footer className="sec-foot">
        <button className="sec-sources-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          <IconChevron size={13} style={{ transform: open ? "rotate(90deg)" : undefined, transition: "transform 0.15s" }} />
          Sources
          {(Object.keys(counts) as Provenance[]).map((p) => (
            <span key={p} className={`prov ${p}`}>{PROV_LABEL[p]} {counts[p]}</span>
          ))}
          {section.claims.length === 0 && <span>none</span>}
        </button>
        {!editing && (
          <div className="sec-actions no-print">
            <button className="btn ghost sm" disabled={disabled} onClick={() => { setDraft(section.body_md); setEditing(true); }}>
              <IconEdit size={14} /> Edit
            </button>
            {section.status !== "confirmed" && (
              <button className="btn primary sm" disabled={disabled} onClick={confirm}>
                <IconCheck size={14} /> Confirm
              </button>
            )}
          </div>
        )}
      </footer>

      {section.claims.length > 0 && (
        <ul className={`claims ${open ? "" : "print-only"}`}>
          {section.claims.map((c, i) => (
            <li key={i}>
              <span className={`prov ${c.provenance}`}>{PROV_LABEL[c.provenance]}</span>
              <span>
                {c.text}
                {c.source_ids.map((sid) => {
                  const s = sources.get(sid);
                  if (!s) return null;
                  return s.url ? (
                    <a key={sid} href={s.url} target="_blank" rel="noreferrer"><IconLink size={11} /> {s.title || s.url}</a>
                  ) : (
                    <span key={sid} className="muted small"> · {s.title}</span>
                  );
                })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
