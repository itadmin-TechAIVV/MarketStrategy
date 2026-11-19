import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { IconArrowRight, IconDoc, IconGlobe, IconMenu, IconSpark, IconTarget } from "../components/Icons";
import { useShell } from "./AppShell";

/** "acme-labs.io" -> "Acme Labs" */
export function nameFromUrl(raw: string): string {
  try {
    const host = new URL(raw.includes("://") ? raw : `https://${raw}`).hostname.replace(/^www\./, "");
    const base = host.split(".").slice(0, -1).join(" ") || host;
    return base.replace(/[-_.]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  } catch {
    return "";
  }
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function NewStrategy() {
  const { user } = useAuth();
  const { refreshWorkspaces, openSidebar } = useShell();
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const suggested = nameFromUrl(url);

  async function start(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError("");
    try {
      const ws = await api.createWorkspace((name || suggested || url).trim(), url.trim());
      await refreshWorkspaces();
      navigate(`/app/w/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start");
      setBusy(false);
    }
  }

  return (
    <div className="conv">
      <div className="conv-header home-mobile-bar">
        <button className="icon-btn" onClick={openSidebar} aria-label="Open menu">
          <IconMenu />
        </button>
      </div>
      <div className="home">
        <div className="home-inner">
          <div className="home-hero">
            <div className="orb"><IconSpark size={26} /></div>
            <h1>
              {greeting()}, {user?.name.split(" ")[0]}. Which product are we taking to market?
            </h1>
            <p>Paste its website. I'll read it, tell you what I understood, and we'll build the strategy together.</p>
          </div>

          <form className="start-box" onSubmit={start}>
            <div className="start-row">
              <IconGlobe size={20} />
              <input
                autoFocus
                placeholder="https://yourproduct.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                aria-label="Product website"
              />
              <button className="btn primary" disabled={busy || !url.trim()}>
                {busy ? "Starting…" : "Start"} <IconArrowRight size={16} />
              </button>
            </div>
            <div className="start-sub">
              <label htmlFor="pname">Product name</label>
              <input id="pname" placeholder={suggested || "Optional, I'll use the domain"} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          </form>
          {error && <div className="alert error">{error}</div>}

          <div className="how-cards">
            <div className="how-card">
              <strong><IconGlobe size={16} /> I read your site</strong>
              Home plus up to 25 key pages: pricing, product, customers, use cases.
            </div>
            <div className="how-card">
              <strong><IconDoc size={16} /> You confirm the brief</strong>
              Every claim sourced, with confidence. Correct anything in one click.
            </div>
            <div className="how-card">
              <strong><IconTarget size={16} /> We build the strategy</strong>
              ICP first, then personas, value, messaging and a 90-day plan.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
