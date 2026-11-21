import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { api, DEMO, type Workspace } from "../api";
import { useAuth } from "../auth";
import { IconChevronUp, IconLock, IconLogout, IconPlus, IconSearch, IconSettings, IconX } from "../components/Icons";
import JackAvatar from "../components/JackAvatar";
import Logo from "../components/Logo";
import { THEMES, useTheme } from "../theme";
import JackPanel from "./jack/JackPanel";
import SettingsDialog, { type SettingsTab } from "./settings/SettingsDialog";
import { savePreference } from "./settings/prefs";

export interface ShellContext {
  workspaces: Workspace[] | null;
  refreshWorkspaces: () => Promise<void>;
  openSidebar: () => void;
  openJack: () => void;
  openSettings: (tab?: SettingsTab) => void;
}

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>();
}

// Muted, varied avatar colours for strategies (no single brand colour).
const PALETTE = ["#1a73e8", "#188038", "#e37400", "#d93025", "#00796b", "#5f6368", "#b06000"];
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

const greetedKey = (userId: string) => `gtm.jack.greeted.${userId}`;

export default function AppShell() {
  const { user, logout, setUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [query, setQuery] = useState("");
  const [sbOpen, setSbOpen] = useState(false);
  const [jackOpen, setJackOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
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

  // The theme saved on the account wins once per sign-in, so it follows the user across devices.
  const syncedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!user || syncedFor.current === user.id) return;
    syncedFor.current = user.id;
    const saved = user.preferences?.theme;
    if (saved && saved !== theme) setTheme(saved);
  }, [user, theme, setTheme]);

  // During the first days, Jack says hello once per browser session after login.
  const onboardingActive = Boolean(user?.onboarding?.active);
  const autostart = user?.preferences?.jack_autostart !== false;
  useEffect(() => {
    if (!user || !onboardingActive || !autostart) return;
    const key = greetedKey(user.id);
    try {
      if (sessionStorage.getItem(key) === "1") return;
    } catch {
      /* storage unavailable: greet anyway */
    }
    // The flag is written only when Jack actually opens, so a cancelled timer doesn't count as a greeting.
    const t = window.setTimeout(() => {
      try {
        sessionStorage.setItem(key, "1");
      } catch {
        /* ignore */
      }
      setJackOpen(true);
    }, 700);
    return () => window.clearTimeout(t);
  }, [user?.id, onboardingActive, autostart]);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const filtered = useMemo(
    () => (workspaces ?? []).filter((w) => w.product_name.toLowerCase().includes(query.trim().toLowerCase())),
    [workspaces, query],
  );

  const openSettings = useCallback((tab: SettingsTab = "profile") => {
    setMenuOpen(false);
    setSettingsTab(tab);
  }, []);
  const openJack = useCallback(() => {
    setMenuOpen(false);
    setJackOpen(true);
  }, []);
  const closeJack = useCallback(() => setJackOpen(false), []);
  const closeSettings = useCallback(() => setSettingsTab(null), []);

  const initials = (user?.name || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  const ctx: ShellContext = { workspaces, refreshWorkspaces, openSidebar: () => setSbOpen(true), openJack, openSettings };
  const ob = user?.onboarding;

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

        <div className="sb-foot">
          <button className={`sb-jack ${jackOpen ? "on" : ""}`} onClick={() => setJackOpen((o) => !o)} aria-expanded={jackOpen}>
            <JackAvatar size={30} />
            <span className="sb-jack-text">
              <strong>Ask Jack</strong>
              <small>{ob?.active ? `Getting started · day ${ob.day} of ${ob.total_days}` : "Your guide to the app"}</small>
            </span>
            {ob?.active && <span className="sb-jack-dot" aria-hidden="true" />}
          </button>

          <div className="sb-user-wrap" ref={menuRef}>
            {menuOpen && (
              <div className="user-menu" role="menu">
                <div className="user-menu-head">
                  <span className="avatar">{initials}</span>
                  <span>
                    <strong>{user?.name}</strong>
                    <small>{user?.email}</small>
                  </span>
                </div>
                <button role="menuitem" onClick={() => openSettings("profile")}>
                  <IconSettings size={16} /> Settings
                </button>
                <button role="menuitem" onClick={() => openSettings("security")}>
                  <IconLock size={16} /> Change password
                </button>
                <button role="menuitem" onClick={openJack}>
                  <JackAvatar size={16} /> Ask Jack
                </button>
                <div className="user-menu-theme" role="radiogroup" aria-label="Theme">
                  {THEMES.map((t) => (
                    <button
                      key={t.id}
                      role="radio"
                      aria-checked={theme === t.id}
                      className={theme === t.id ? "on" : ""}
                      onClick={() => {
                        setTheme(t.id);
                        void savePreference({ theme: t.id }, (p) => {
                          if (user) setUser({ ...user, preferences: p });
                        });
                      }}
                    >
                      <span className={`swatch ${t.id}`} /> {t.label}
                    </button>
                  ))}
                </div>
                <button
                  role="menuitem"
                  className="danger"
                  onClick={() => {
                    logout();
                    navigate("/");
                  }}
                >
                  <IconLogout size={16} /> Log out
                </button>
              </div>
            )}
            <button
              className={`sb-user ${menuOpen ? "on" : ""}`}
              onClick={() => setMenuOpen((o) => !o)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <span className="avatar">{initials}</span>
              <span className="sb-user-text">
                <strong>{user?.name}</strong>
                <span>{DEMO ? "Demo · sample data" : user?.organization.name}</span>
              </span>
              <IconChevronUp size={16} className="sb-user-chev" />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet context={ctx} />
      </main>
      {jackOpen && <JackPanel workspaces={workspaces} onClose={closeJack} onOpenSettings={openSettings} />}
      {settingsTab && (
        <SettingsDialog
          tab={settingsTab}
          onTab={setSettingsTab}
          onClose={closeSettings}
          onOpenJack={() => {
            setSettingsTab(null);
            setJackOpen(true);
          }}
        />
      )}
    </div>
  );
}
