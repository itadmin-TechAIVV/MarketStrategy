import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { api, DEMO, type Workspace } from "../api";
import { useAuth } from "../auth";
import { IconLogout, IconPlus, IconSearch, IconX } from "../components/Icons";
import Logo from "../components/Logo";

export interface ShellContext {
  workspaces: Workspace[] | null;
  refreshWorkspaces: () => Promise<void>;
  openSidebar: () => void;
}

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>();
}

const PALETTE = ["#7c3aed", "#db2777", "#0891b2", "#ea580c", "#059669", "#4f46e5", "#ca8a04"];
export function colorFor(id: string): string {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

const STAGE_SHORT: Record<string, string> = {
  brief: "Brief", icp: "ICP", personas: "Personas", value: "Value", competition: "Competition", sizing: "Sizing",
  difficulty: "Difficulty", channels: "Channels", messaging: "Messaging", pricing: "Pricing", plan: "90-day plan",
};

function groupByDate(items: Workspace[]): [string, Workspace[]][] {
  const now = Date.now();
  const groups: Record<string, Workspace[]> = {};
  for (const w of items) {
    const days = (now - new Date(w.updated_at || w.created_at).getTime()) / 86_400_000;
    const g = days < 1 ? "Today" : days < 7 ? "This week" : days < 30 ? "This month" : "Older";
    (groups[g] ||= []).push(w);
  }
  return ["Today", "This week", "This month", "Older"].filter((g) => groups[g]).map((g) => [g, groups[g]]);
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [query, setQuery] = useState("");
  const [sbOpen, setSbOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const refreshWorkspaces = useCallback(async () => {
    try {
      setWorkspaces(await api.listWorkspaces());
    } catch {
      setWorkspaces((w) => w ?? []);
    }
  }, []);

  useEffect(() => {
    void refreshWorkspaces();
  }, [refreshWorkspaces]);

  useEffect(() => setSbOpen(false), [location.pathname]);

  const filtered = useMemo(
    () => (workspaces ?? []).filter((w) => w.product_name.toLowerCase().includes(query.trim().toLowerCase())),
    [workspaces, query],
  );

  const initials = (user?.name || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  const ctx: ShellContext = { workspaces, refreshWorkspaces, openSidebar: () => setSbOpen(true) };

  return (
    <div className={`app ${sbOpen ? "sb-open" : ""}`}>
      <div className="sb-backdrop" onClick={() => setSbOpen(false)} />
      <aside className="sidebar">
        <div className="sb-top">
          <Logo to="/app" />
          <button className="icon-btn mobile-only" onClick={() => setSbOpen(false)} aria-label="Close menu">
            <IconX />
          </button>
        </div>
        <Link to="/app" className="btn secondary sb-new">
          <IconPlus size={17} /> New strategy
        </Link>
        <div className="sb-search">
          <IconSearch size={15} />
          <input placeholder="Search strategies" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search strategies" />
        </div>
        <nav className="sb-list">
          {workspaces === null ? (
            <div className="sb-empty">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="sb-empty">{query ? "No matches." : "No strategies yet. Start one with your product's website."}</div>
          ) : (
            groupByDate(filtered).map(([group, items]) => (
              <div key={group}>
                <div className="sb-group">{group}</div>
                {items.map((w) => (
                  <NavLink key={w.id} to={`/app/w/${w.id}`} className={({ isActive }) => `sb-item ${isActive ? "active" : ""}`}>
                    <span className="sb-item-icon" style={{ background: colorFor(w.id) }}>
                      {w.product_name.trim().charAt(0).toUpperCase()}
                    </span>
                    <span className="sb-item-text">
                      <span>{w.product_name}</span>
                      <small>{STAGE_SHORT[w.current_stage] ?? w.current_stage}</small>
                    </span>
                  </NavLink>
                ))}
              </div>
            ))
          )}
        </nav>
        <div className="sb-user">
          <span className="avatar">{initials}</span>
          <span className="sb-user-text">
            <strong>{user?.name}</strong>
            <span>{DEMO ? "Demo · sample data" : user?.organization.name}</span>
          </span>
          <button
            className="icon-btn"
            title="Log out"
            aria-label="Log out"
            onClick={() => {
              logout();
              navigate("/");
            }}
          >
            <IconLogout size={17} />
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet context={ctx} />
      </main>
    </div>
  );
}
