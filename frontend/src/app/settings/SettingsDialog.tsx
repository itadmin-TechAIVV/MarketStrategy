import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, DEMO, type Preferences } from "../../api";
import { useAuth } from "../../auth";
import { IconCheck, IconEye, IconEyeOff, IconInfo, IconLock, IconPalette, IconUser, IconX } from "../../components/Icons";
import JackAvatar from "../../components/JackAvatar";
import { THEMES, useTheme } from "../../theme";
import { savePreference } from "./prefs";

export type SettingsTab = "profile" | "security" | "appearance" | "jack" | "about";

const TABS: { id: SettingsTab; label: string; icon: ReactNode }[] = [
  { id: "profile", label: "Profile", icon: <IconUser size={17} /> },
  { id: "security", label: "Password & security", icon: <IconLock size={17} /> },
  { id: "appearance", label: "Appearance", icon: <IconPalette size={17} /> },
  { id: "jack", label: "Jack, your guide", icon: <JackAvatar size={18} /> },
  { id: "about", label: "About", icon: <IconInfo size={17} /> },
];

interface Props {
  tab: SettingsTab;
  onTab: (t: SettingsTab) => void;
  onClose: () => void;
  onOpenJack: () => void;
}

export default function SettingsDialog({ tab, onTab, onClose, onOpenJack }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="settings" role="dialog" aria-modal="true" aria-label="Settings" tabIndex={-1} ref={panelRef}>
        <nav className="settings-nav" aria-label="Settings sections">
          <h2>Settings</h2>
          {TABS.map((t) => (
            <button key={t.id} className={`settings-tab ${tab === t.id ? "on" : ""}`} onClick={() => onTab(t.id)}>
              <span className="settings-tab-icon">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>
        <section className="settings-body">
          <button className="icon-btn settings-close" onClick={onClose} aria-label="Close settings">
            <IconX />
          </button>
          {tab === "profile" && <ProfileTab />}
          {tab === "security" && <SecurityTab />}
          {tab === "appearance" && <AppearanceTab />}
          {tab === "jack" && <JackTab onOpenJack={onOpenJack} />}
          {tab === "about" && <AboutTab />}
        </section>
      </div>
    </div>
  );
}

function Head({ title, sub }: { title: string; sub: string }) {
  return (
    <header className="settings-head">
      <h3>{title}</h3>
      <p>{sub}</p>
    </header>
  );
}

function Status({ ok, error }: { ok: string; error: string }) {
  if (error) return <div className="alert error">{error}</div>;
  if (ok) return <div className="alert ok"><IconCheck size={15} /> {ok}</div>;
  return null;
}

function formatDate(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

/* ---------------------------------------------------------------- profile */
function ProfileTab() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [org, setOrg] = useState(user?.organization.name ?? "");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");
  if (!user) return null;
  const isAdmin = user.role === "admin";
  const dirty = name.trim() !== user.name || (isAdmin && org.trim() !== user.organization.name);
  const initials = (name || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setOk("");
    setError("");
    try {
      const body: { name?: string; organization_name?: string } = { name: name.trim() };
      if (isAdmin && org.trim() !== user!.organization.name) body.organization_name = org.trim();
      setUser(await api.updateProfile(body));
      setOk("Profile saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="settings-pane" onSubmit={save}>
      <Head title="Profile" sub="How you appear in the app and to your team." />
      <div className="profile-card">
        <span className="avatar xl">{initials}</span>
        <div>
          <strong>{name || user.name}</strong>
          <span>{user.email}</span>
          <span className="chip gray">{user.role === "admin" ? "Admin" : "Member"}</span>
        </div>
      </div>
      <label className="field">
        Full name
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
      </label>
      <label className="field">
        Email
        <input className="input" value={user.email} disabled />
        <span className="field-hint">Your email is your login and can't be changed here.</span>
      </label>
      <label className="field">
        Organisation
        <input className="input" value={org} onChange={(e) => setOrg(e.target.value)} disabled={!isAdmin} maxLength={120} required />
        {!isAdmin && <span className="field-hint">Only an admin can rename the organisation.</span>}
      </label>
      <dl className="facts">
        <div><dt>Member since</dt><dd>{formatDate(user.created_at)}</dd></div>
        <div><dt>First login</dt><dd>{formatDate(user.first_login_at)}</dd></div>
      </dl>
      <Status ok={ok} error={error} />
      <div className="settings-actions">
        <button className="btn primary" disabled={busy || !dirty || !name.trim()}>{busy ? "Saving…" : "Save changes"}</button>
      </div>
    </form>
  );
}

/* ---------------------------------------------------------------- security */
function strength(pw: string): { score: number; label: string } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const capped = Math.min(4, score);
  return { score: capped, label: ["Too short", "Weak", "Fair", "Good", "Strong"][capped] };
}

function PasswordInput({ label, value, onChange, auto }: { label: string; value: string; onChange: (v: string) => void; auto: string }) {
  const [show, setShow] = useState(false);
  return (
    <label className="field">
      {label}
      <span className="pw-wrap">
        <input className="input" type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} autoComplete={auto} required />
        <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}>
          {show ? <IconEyeOff size={16} /> : <IconEye size={16} />}
        </button>
      </span>
    </label>
  );
}

function SecurityTab() {
  const { user, replaceSession } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");
  const s = strength(next);
  const mismatch = confirm.length > 0 && confirm !== next;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setOk("");
    setError("");
    try {
      const res = await api.changePassword(current, next);
      replaceSession(res.token, res.user);
      setCurrent("");
      setNext("");
      setConfirm("");
      setOk("Password changed. Other devices have been signed out.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="settings-pane" onSubmit={submit}>
      <Head title="Password & security" sub="Change your password. Every other device you're signed in on will be signed out." />
      {DEMO && <div className="demo-note">Demo mode: nothing is really changed.</div>}
      <input type="text" autoComplete="username" value={user?.email ?? ""} readOnly hidden />
      <PasswordInput label="Current password" value={current} onChange={setCurrent} auto="current-password" />
      <PasswordInput label="New password" value={next} onChange={setNext} auto="new-password" />
      {next && (
        <div className={`pw-meter s${s.score}`} aria-live="polite">
          <span className="pw-bars">{[1, 2, 3, 4].map((i) => <i key={i} className={i <= s.score ? "on" : ""} />)}</span>
          {s.label}
        </div>
      )}
      <PasswordInput label="Confirm new password" value={confirm} onChange={setConfirm} auto="new-password" />
      {mismatch && <span className="field-error">The passwords don't match.</span>}
      <ul className="pw-rules">
        <li className={next.length >= 8 ? "met" : ""}><IconCheck size={13} /> At least 8 characters</li>
        <li className={/[A-Za-z]/.test(next) && /[^A-Za-z]/.test(next) ? "met" : ""}><IconCheck size={13} /> Letters plus numbers or symbols</li>
        <li className={next && next !== current ? "met" : ""}><IconCheck size={13} /> Different from your current password</li>
      </ul>
      <Status ok={ok} error={error} />
      <div className="settings-actions">
        <span className="muted small">Last changed: {formatDate(user?.password_changed_at) === "—" ? "never" : formatDate(user?.password_changed_at)}</span>
        <button className="btn primary" disabled={busy || !current || next.length < 8 || mismatch || !confirm}>
          {busy ? "Changing…" : "Change password"}
        </button>
      </div>
    </form>
  );
}

/* ---------------------------------------------------------------- appearance */
function AppearanceTab() {
  const { theme, setTheme } = useTheme();
  const { user, setUser } = useAuth();
  const apply = (p: Preferences) => user && setUser({ ...user, preferences: p });

  return (
    <div className="settings-pane">
      <Head title="Appearance" sub="Pick the look you like. It follows you to every device you sign in on." />
      <div className="theme-cards" role="radiogroup" aria-label="Theme">
        {THEMES.map((t) => (
          <button
            key={t.id}
            role="radio"
            aria-checked={theme === t.id}
            className={`theme-card ${theme === t.id ? "on" : ""}`}
            onClick={() => {
              setTheme(t.id);
              void savePreference({ theme: t.id }, apply);
            }}
          >
            <span className={`theme-preview ${t.id}`}>
              <span className="tp-side"><i /><i /><i /></span>
              <span className="tp-main"><b /><i /><i /><em /></span>
            </span>
            <span className="theme-card-label">
              <strong>{t.label}</strong>
              <small>{t.hint}</small>
            </span>
            {theme === t.id && <span className="theme-check"><IconCheck size={13} strokeWidth={3} /></span>}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- jack */
function JackTab({ onOpenJack }: { onOpenJack: () => void }) {
  const { user, setUser } = useAuth();
  const [cleared, setCleared] = useState(false);
  if (!user) return null;
  const prefs = user.preferences ?? { theme: "material", jack_autostart: true };
  const ob = user.onboarding;

  return (
    <div className="settings-pane">
      <Head title="Jack, your guide" sub="Jack knows how the app works and what's in your account. Ask him anything, any time." />
      <div className="jack-hero">
        <JackAvatar size={48} />
        <div>
          <strong>Hi {user.name.split(" ")[0]}, I'm Jack.</strong>
          <span>
            {ob?.active
              ? `You're on day ${ob.day} of ${ob.total_days} of getting started, so I'll say hello after you log in.`
              : "Your first days are behind you. I'm still here whenever you need me."}
          </span>
        </div>
      </div>
      {ob && (
        <div className="onboard-track" aria-label={`Day ${Math.min(ob.day, ob.total_days)} of ${ob.total_days}`}>
          {Array.from({ length: ob.total_days }, (_, i) => (
            <i key={i} className={i < ob.day ? "on" : ""} />
          ))}
        </div>
      )}
      <label className="toggle-row">
        <span>
          <strong>Greet me after I log in</strong>
          <small>During your first {ob?.total_days ?? 10} days, Jack opens by himself with a hello and a next step.</small>
        </span>
        <input
          type="checkbox"
          className="switch"
          checked={prefs.jack_autostart}
          onChange={(e) =>
            void savePreference({ jack_autostart: e.target.checked }, (p) => setUser({ ...user, preferences: p }))
          }
        />
      </label>
      <div className="settings-actions">
        <button
          className="btn ghost"
          onClick={async () => {
            await api.clearJack().catch(() => undefined);
            setCleared(true);
          }}
        >
          {cleared ? "Chat cleared" : "Clear chat history"}
        </button>
        <button className="btn primary" onClick={onOpenJack}>Talk to Jack</button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- about */
function AboutTab() {
  return (
    <div className="settings-pane">
      <Head title="About" sub="GTM Strategy, an AI agent that builds your go-to-market strategy with you." />
      <dl className="facts">
        <div><dt>Version</dt><dd>0.2.0</dd></div>
        <div><dt>AI model</dt><dd>Google Gemini</dd></div>
      </dl>
      <h4 className="settings-sub">Keyboard</h4>
      <dl className="facts keys">
        <div><dt>Send a message</dt><dd><kbd>Enter</kbd></dd></div>
        <div><dt>New line</dt><dd><kbd>Shift</kbd> + <kbd>Enter</kbd></dd></div>
        <div><dt>Close a dialog or Jack</dt><dd><kbd>Esc</kbd></dd></div>
      </dl>
    </div>
  );
}
