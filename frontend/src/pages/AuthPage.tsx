import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { DEMO } from "../api";
import { useAuth } from "../auth";
import { IconCheck } from "../components/Icons";
import Logo from "../components/Logo";

export default function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { user, login, signup } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ organization_name: "", name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/app" replace />;

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(form.email, form.password);
      else await signup(form);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <aside className="auth-art">
        <Logo />
        <div>
          <blockquote>“Tell me plainly what you understood, and ask me only what you can't know.”</blockquote>
          <div className="auth-points">
            <div><IconCheck size={18} /> Reads your website and cites every claim</div>
            <div><IconCheck size={18} /> Confirms the brief with you, section by section</div>
            <div><IconCheck size={18} /> Builds your ICP and strategy one stage at a time</div>
          </div>
        </div>
        <span className="auth-foot">Your workspaces are private to your organisation.</span>
      </aside>

      <div className="auth-form-wrap">
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-mobile-logo">
            <Logo />
          </div>
          <div>
            <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          </div>
          <p className="sub">
            {mode === "login" ? "Log in to continue your strategies." : "Start building your go-to-market strategy in minutes."}
          </p>
          {DEMO && <div className="demo-note">Demo mode: any email and password will work.</div>}
          {mode === "signup" && (
            <>
              <label className="field">
                Company name
                <input className="input" required value={form.organization_name} onChange={set("organization_name")} placeholder="Acme Inc." />
              </label>
              <label className="field">
                Your name
                <input className="input" required value={form.name} onChange={set("name")} placeholder="Jane Doe" autoComplete="name" />
              </label>
            </>
          )}
          <label className="field">
            Work email
            <input className="input" type="email" required autoComplete="email" value={form.email} onChange={set("email")} placeholder="you@company.com" />
          </label>
          <label className="field">
            Password
            <input
              className="input"
              type="password"
              required
              minLength={mode === "signup" ? 8 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={form.password}
              onChange={set("password")}
              placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
            />
          </label>
          {error && <div className="alert error">{error}</div>}
          <button className="btn primary lg" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </button>
          <p className="auth-switch">
            {mode === "login" ? (
              <>New here? <Link to="/signup">Create an account</Link></>
            ) : (
              <>Already have an account? <Link to="/login">Log in</Link></>
            )}
          </p>
        </form>
      </div>
    </div>
  );
}
