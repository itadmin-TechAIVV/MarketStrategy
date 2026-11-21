/** Jack's face: a friendly round mark in the theme's accent colour. */
export default function JackAvatar({ size = 32, wave = false }: { size?: number; wave?: boolean }) {
  return (
    <span className={`jack-avatar ${wave ? "wave" : ""}`} style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 40 40" width={size} height={size}>
        <circle cx="20" cy="20" r="20" className="jack-face" />
        <circle cx="20" cy="20" r="20" fill="url(#jack-shine)" />
        <ellipse cx="14.5" cy="18" rx="2.2" ry="2.8" className="jack-eye" />
        <ellipse cx="25.5" cy="18" rx="2.2" ry="2.8" className="jack-eye" />
        <path d="M13.5 25c1.8 2.4 4 3.6 6.5 3.6s4.7-1.2 6.5-3.6" className="jack-smile" />
        <defs>
          <radialGradient id="jack-shine" cx="0.3" cy="0.25" r="0.8">
            <stop offset="0" stopColor="#fff" stopOpacity="0.35" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
        </defs>
      </svg>
    </span>
  );
}
