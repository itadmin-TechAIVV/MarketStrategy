import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "material" | "warm";
export const THEMES: { id: Theme; label: string; hint: string }[] = [
  { id: "material", label: "Material", hint: "Clean and bright, Google Sans" },
  { id: "warm", label: "Warm", hint: "Soft paper tones, serif headings" },
];

const KEY = "gtm.theme";
const ThemeContext = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "material", setTheme: () => {} });

function initial(): Theme {
  try {
    const t = localStorage.getItem(KEY);
    if (t === "material" || t === "warm") return t;
  } catch {
    /* storage unavailable */
  }
  return "material";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);

/** Two-option segmented control. */
export function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();
  return (
    <div className={`theme-switch ${compact ? "compact" : ""}`} role="radiogroup" aria-label="Theme">
      {THEMES.map((t) => (
        <button
          key={t.id}
          type="button"
          role="radio"
          aria-checked={theme === t.id}
          title={t.hint}
          className={theme === t.id ? "on" : ""}
          onClick={() => setTheme(t.id)}
        >
          <span className={`swatch ${t.id}`} />
          {t.label}
        </button>
      ))}
    </div>
  );
}
