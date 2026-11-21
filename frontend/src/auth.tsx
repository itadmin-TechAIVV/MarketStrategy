import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: { organization_name: string; name: string; email: string; password: string }) => Promise<void>;
  logout: () => void;
  /** Replace the signed-in user (after a profile or preference change). */
  setUser: (user: User) => void;
  /** Swap in a new session token, e.g. after a password change. */
  replaceSession: (token: string, user: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => logout())
      .finally(() => setLoading(false));
  }, [logout]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      logout,
      setUser,
      replaceSession: (token, next) => {
        setToken(token);
        setUser(next);
      },
      login: async (email, password) => {
        const res = await api.login(email, password);
        setToken(res.token);
        setUser(res.user);
      },
      signup: async (data) => {
        const res = await api.signup(data);
        setToken(res.token);
        setUser(res.user);
      },
    }),
    [user, loading, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
