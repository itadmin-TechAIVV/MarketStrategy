// Typed API client. The backend URL comes from VITE_API_URL (set it in Vercel).
import { demoApi, demoStreamChat } from "./demo";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";

const TOKEN_KEY = "gtm.token";

/** Demo mode: sample data, no backend (set VITE_DEMO=true). */
export const DEMO = import.meta.env.VITE_DEMO === "true";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (res.status === 401) {
    onUnauthorized();
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") || "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

// ------------------------------------------------------------------ types
export type ThemeName = "material" | "warm";

export interface Preferences {
  theme: ThemeName;
  /** Jack opens by himself after login while onboarding is active. */
  jack_autostart: boolean;
}

export interface Onboarding {
  day: number;
  days_left: number;
  total_days: number;
  active: boolean;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  organization: { id: string; name: string };
  created_at?: string | null;
  first_login_at?: string | null;
  password_changed_at?: string | null;
  preferences?: Preferences;
  onboarding?: Onboarding;
}

export type JackAction = "none" | "new_strategy" | "open_strategy" | "open_settings" | "open_security";

export interface JackMessage {
  id: string;
  role: "user" | "jack";
  text: string;
  suggestions: string[];
  action: JackAction;
  strategy_id: string;
  action_label: string;
  created_at: string;
}

export interface Question {
  id: string;
  text: string;
  options: string[];
  allow_free_text: boolean;
  multi_select: boolean;
}

export interface Ask {
  intro: string;
  questions: Question[];
  section_key?: string | null;
}

export interface Workspace {
  id: string;
  product_name: string;
  website_url: string;
  current_stage: string;
  crawl: { status: string; pages?: number; stopped_reason?: string; error?: string } | null;
  pending_ask: Ask | null;
  busy: boolean;
  created_at: string;
  updated_at: string;
}

export type Provenance = "website" | "user" | "assumption";
export interface Claim {
  text: string;
  provenance: Provenance;
  source_ids: string[];
}

export type SectionStatus = "draft" | "confirmed" | "needs_refresh";
export interface Section {
  id: string;
  key: string;
  stage: string;
  title: string;
  body_md: string;
  claims: Claim[];
  confidence: "High" | "Medium" | "Low";
  status: SectionStatus;
  version: number;
  updated_by: "agent" | "user";
  user_edited: boolean;
  refresh_reason: string | null;
}

export interface Stage {
  key: string;
  title: string;
  ready: boolean;
  optional: boolean;
  status: "not_started" | "in_progress" | "confirmed" | "needs_refresh";
  sections: { key: string; title: string; hint: string }[];
}

export interface WorkspaceDetail {
  workspace: Workspace;
  stages: Stage[];
  sections: Section[];
}

export interface Source {
  source_id: string;
  kind: string;
  url: string | null;
  title: string;
  page_type: string;
}

export interface TranscriptItem {
  role: "user" | "assistant";
  kind: "text" | "answer" | "ask";
  text?: string;
  ask?: Ask;
  seq: number;
}

export type AnswerMap = Record<string, { selected: string[]; text: string }>;

export type AgentEvent =
  | { type: "text"; text: string }
  | { type: "block_end" }
  | { type: "tool"; name: string; status: "start" | "done" | "error"; label: string }
  | { type: "crawl"; status: string; fetched?: number; url?: string; title?: string; error?: string }
  | { type: "section"; section: Section }
  | { type: "sections_changed" | "workspace_changed" | "sources_changed" }
  | { type: "ask"; ask: Ask }
  | { type: "error"; message: string }
  | { type: "done" };

// ------------------------------------------------------------------ calls
export const api = {
  signup: (body: { organization_name: string; name: string; email: string; password: string }) =>
    request<{ token: string; user: User }>("/api/auth/signup", { method: "POST", body: JSON.stringify(body) }),
  login: (email: string, password: string) =>
    request<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<User>("/api/auth/me"),

  updateProfile: (body: { name?: string; organization_name?: string }) =>
    request<User>("/api/account/profile", { method: "PATCH", body: JSON.stringify(body) }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ token: string; user: User }>("/api/account/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  updatePreferences: (body: Partial<Preferences>) =>
    request<Preferences>("/api/account/preferences", { method: "PATCH", body: JSON.stringify(body) }),

  jackMessages: () => request<JackMessage[]>("/api/jack/messages"),
  askJack: (text: string, page: { path: string; strategy_id?: string | null }) =>
    request<{ user: JackMessage; jack: JackMessage }>("/api/jack/messages", {
      method: "POST",
      body: JSON.stringify({ text, page }),
    }),
  clearJack: () => request<void>("/api/jack/messages", { method: "DELETE" }),

  listWorkspaces: () => request<Workspace[]>("/api/workspaces"),
  createWorkspace: (product_name: string, website_url: string) =>
    request<Workspace>("/api/workspaces", { method: "POST", body: JSON.stringify({ product_name, website_url }) }),
  deleteWorkspace: (id: string) => request<void>(`/api/workspaces/${id}`, { method: "DELETE" }),
  workspace: (id: string) => request<WorkspaceDetail>(`/api/workspaces/${id}`),
  transcript: (id: string) => request<TranscriptItem[]>(`/api/workspaces/${id}/messages`),
  sources: (id: string) => request<Source[]>(`/api/workspaces/${id}/sources`),
  addContext: (id: string, title: string, text: string) =>
    request<Source>(`/api/workspaces/${id}/sources`, { method: "POST", body: JSON.stringify({ title, text }) }),
  editSection: (id: string, key: string, body_md: string) =>
    request<{ section: Section; flagged: string[] }>(`/api/workspaces/${id}/sections/${key}`, {
      method: "PATCH",
      body: JSON.stringify({ body_md }),
    }),
  confirmSection: (id: string, key: string) =>
    request<Section>(`/api/workspaces/${id}/sections/${key}/confirm`, { method: "POST" }),
  exportMarkdown: (id: string) => request<string>(`/api/workspaces/${id}/export.md`),
};

if (DEMO) Object.assign(api, demoApi);

/** POST a chat turn and read the Server-Sent Events stream. */
export async function streamChat(
  workspaceId: string,
  body: { text?: string; answers?: AnswerMap },
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (DEMO) return demoStreamChat(workspaceId, body, onEvent);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}/api/workspaces/${workspaceId}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401) onUnauthorized();
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          try {
            onEvent(JSON.parse(line.slice(6)) as AgentEvent);
          } catch {
            /* malformed event: skip */
          }
        }
      }
    }
  }
}
