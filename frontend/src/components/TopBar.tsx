import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { DEMO } from "../api";
import { useAuth } from "../auth";

export default function TopBar({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <header className="topbar no-print">
      <Link to="/" className="brand">
        <span className="brand-mark">◆</span> GTM Strategy
      </Link>
      {DEMO && <span className="demo-tag">Demo · sample data</span>}
      <div className="topbar-mid">{children}</div>
      <div className="topbar-user">
        <span className="muted">
          {user?.name} · {user?.organization.name}
        </span>
        <button className="btn ghost small" onClick={logout}>
          Log out
        </button>
      </div>
    </header>
  );
}
