import { Link } from "react-router-dom";

/** Logo mark: a rising line in a rounded square, drawn in the theme's accent colour. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="logo-mark">
      <rect width="32" height="32" rx="9" style={{ fill: "var(--accent)" }} />
      <path d="M9 21l5-6 4 4 5-8" stroke="var(--on-accent)" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="logo">
      <LogoMark />
      <span>
        GTM Strategy<span className="logo-sub">AI agent</span>
      </span>
    </Link>
  );
}
