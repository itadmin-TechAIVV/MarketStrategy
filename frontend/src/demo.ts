// Demo mode (VITE_DEMO=true): the real UI with sample data and no backend.
// Everything here is fictional ("Northwind Payroll" on a .example domain).
import type {
  AgentEvent,
  AnswerMap,
  Ask,
  Claim,
  Section,
  Source,
  Stage,
  TranscriptItem,
  User,
  Workspace,
  WorkspaceDetail,
} from "./api";

const WS_ID = "demo-workspace";
const now = new Date().toISOString();

const user: User = {
  id: "demo-user",
  name: "Demo User",
  email: "demo@northwind.example",
  role: "admin",
  organization: { id: "demo-org", name: "Demo Organisation" },
};

const sources: Source[] = [
  { source_id: "s-home", kind: "crawl", url: "https://northwind.example/", title: "Northwind Payroll – Payroll for clinics", page_type: "home" },
  { source_id: "s-pricing", kind: "crawl", url: "https://northwind.example/pricing", title: "Pricing – Northwind", page_type: "pricing" },
  { source_id: "s-features", kind: "crawl", url: "https://northwind.example/features", title: "Features – Northwind", page_type: "features" },
  { source_id: "s-customers", kind: "crawl", url: "https://northwind.example/customers", title: "Customers – Northwind", page_type: "customers" },
  { source_id: "s-about", kind: "crawl", url: "https://northwind.example/about", title: "About us – Northwind", page_type: "about" },
  { source_id: "s-compare", kind: "crawl", url: "https://northwind.example/compare/spreadsheets", title: "Northwind vs spreadsheets", page_type: "compare" },
];

const w = (text: string, ...ids: string[]): Claim => ({ text, provenance: "website", source_ids: ids });
const u = (text: string): Claim => ({ text, provenance: "user", source_ids: [] });
const a = (text: string): Claim => ({ text, provenance: "assumption", source_ids: [] });

function sec(
  key: string,
  title: string,
  body_md: string,
  claims: Claim[],
  confidence: Section["confidence"],
  status: Section["status"],
  extra: Partial<Section> = {},
): Section {
  return {
    id: key, key, stage: key.split(".")[0], title, body_md, claims, confidence, status,
    version: 1, updated_by: "agent", user_edited: false, refresh_reason: null, ...extra,
  };
}

let sections: Section[] = [
  sec("brief.product", "The product",
    "**Payroll and shift-pay software for independent healthcare clinics.**\n\nNorthwind Payroll runs payroll for clinics with shift-based staff: it imports rota hours, applies overtime and on-call rules, pays staff, and files payroll taxes. It positions itself as the replacement for spreadsheets plus a general-purpose payroll tool.",
    [w("Payroll for independent clinics", "s-home"), w("Imports rota hours and applies overtime rules", "s-features")], "High", "confirmed"),
  sec("brief.problems", "Problems it solves, and for whom",
    "- **Practice managers** lose 1–2 days a month reconciling rota hours with payroll.\n- **Clinic owners** risk under- or over-paying on-call and overtime.\n- **Staff** get late or wrong pay when shifts change.",
    [w("Practice managers spend days reconciling hours", "s-home"), u("Our main buyer is the practice manager, not the owner"), a("The time figure is the site's claim, not measured")], "Medium", "confirmed",
    { user_edited: false }),
  sec("brief.features", "Core features and capabilities",
    "- Rota import (CSV and 3 scheduling tools)\n- Overtime, on-call and holiday-pay rules\n- Payroll runs and payslips\n- Payroll tax filing\n- Staff self-service app",
    [w("Rota import from CSV and scheduling tools", "s-features"), w("Payroll tax filing", "s-features"), w("Staff self-service app", "s-features")], "High", "draft"),
  sec("brief.pricing", "Pricing model",
    "- **Per employee per month**, two tiers: *Essentials* and *Plus*.\n- Prices published; annual billing discount.\n- No free tier; 30-day trial.",
    [w("Per employee per month, two tiers", "s-pricing"), w("30-day trial", "s-pricing")], "High", "draft"),
  sec("brief.audience", "Who it seems built for",
    "- **Industry:** independent clinics (dental, physio, GP, vet)\n- **Size:** 10–150 staff\n- **Roles:** practice manager (user and buyer), clinic owner (signs off)",
    [w("Dental, physio and GP clinics named", "s-customers"), a("10–150 staff inferred from customer logos and tier limits")], "Medium", "draft"),
  sec("brief.proof", "Proof points",
    "- 3 named customer stories (dental groups)\n- \"Payroll in 20 minutes instead of 2 days\" (customer quote)\n- No published customer count",
    [w("Three customer stories", "s-customers"), w("20 minutes instead of 2 days quote", "s-customers")], "Medium", "draft"),
  sec("brief.positioning", "Positioning and tone of voice",
    "- **Positioning:** built for clinics, unlike generic payroll.\n- **Tone:** plain, reassuring, compliance-aware.",
    [w("Built specifically for clinics", "s-home", "s-about")], "Medium", "draft"),
  sec("brief.competitors", "Competitors and alternatives",
    "- **Named:** spreadsheets plus a generic payroll tool\n- **Implied:** general SMB payroll platforms, accountants running payroll\n- **Do nothing:** keep the manual process",
    [w("Compares itself with spreadsheets", "s-compare"), a("General SMB payroll platforms are the real competitors")], "Low", "draft"),
  sec("brief.gaps", "Gaps: what the site does not say",
    "- Which countries and payroll tax regimes are supported\n- Implementation time and who does onboarding\n- Integrations with practice-management software\n- Security and compliance certifications",
    [a("No country coverage stated anywhere on the site")], "High", "draft"),
];

const confirmFeatures: Ask = {
  intro: "Section 3 of 9: **Core features**. Here's what I found on the features page.",
  questions: [
    {
      id: "features_ok",
      text: "Rota import, overtime/on-call rules, payroll runs, tax filing and a staff app. Is that the core feature set?",
      options: ["Looks right (suggested)", "Needs a correction", "Add something missing"],
      allow_free_text: true,
      multi_select: false,
    },
  ],
  section_key: "brief.features",
};

let pendingAsk: Ask | null = confirmFeatures;

let transcript: TranscriptItem[] = [
  { role: "user", kind: "text", seq: 1, text: "Please study our website https://northwind.example and tell me what you understood about Northwind Payroll." },
  { role: "assistant", kind: "text", seq: 2, text: "I read **6 pages** (home, pricing, features, customers, about, and a comparison page) and drafted the brief on the right.\n\n- Strongest evidence: features and pricing (**High** confidence).\n- Weakest: competitors (**Low**, the site only compares itself with spreadsheets).\n- Biggest gap: which **countries and tax regimes** you support.\n\nLet's confirm it one section at a time." },
  { role: "assistant", kind: "ask", seq: 2, ask: { intro: "", questions: [{ id: "q1", text: "Section 1: is the one-liner right?", options: [], allow_free_text: true, multi_select: false }] } },
  { role: "user", kind: "answer", seq: 3, text: "Looks right" },
  { role: "assistant", kind: "ask", seq: 4, ask: { intro: "", questions: [{ id: "q2", text: "Section 2: who feels these problems most?", options: [], allow_free_text: true, multi_select: false }] } },
  { role: "user", kind: "answer", seq: 5, text: "Needs a correction; our main buyer is the practice manager, not the owner" },
  { role: "assistant", kind: "text", seq: 6, text: "Got it. I've recorded **practice manager as the main buyer** as your statement; it overrides the website from now on." },
  { role: "assistant", kind: "ask", seq: 6, ask: confirmFeatures },
];

function stages(): Stage[] {
  const defs: [string, string, boolean, [string, string][]][] = [
    ["brief", "What I understood", true, [
      ["brief.product", "The product"], ["brief.problems", "Problems it solves, and for whom"],
      ["brief.features", "Core features and capabilities"], ["brief.pricing", "Pricing model"],
      ["brief.audience", "Who it seems built for"], ["brief.proof", "Proof points"],
      ["brief.positioning", "Positioning and tone of voice"], ["brief.competitors", "Competitors and alternatives"],
      ["brief.gaps", "Gaps: what the site does not say"]]],
    ["icp", "Ideal Customer Profile", true, [
      ["icp.firmographics", "Firmographics"], ["icp.triggers", "Buying triggers"],
      ["icp.budget_owner", "Budget owner"], ["icp.buying_committee", "Buying committee"]]],
    ["personas", "Personas", false, [["personas.list", "Personas"]]],
    ["value", "True value", false, [["value.per_persona", "Value proposition per persona"]]],
    ["competition", "Competition and alternatives", false, [["competition.landscape", "Direct, indirect, and do-nothing"]]],
    ["sizing", "Market sizing", false, [["sizing.tam_sam_som", "TAM / SAM / SOM"]]],
    ["difficulty", "Difficulty of approach", false, [["difficulty.where_to_start", "Where to start"]]],
    ["channels", "Channels", false, [["channels.ranked", "Channels ranked by fit"]]],
    ["messaging", "Messaging", false, [["messaging.core", "One-liner, elevator pitch, three pillars"]]],
    ["pricing", "Pricing and packaging", false, [["pricing.suggestions", "Pricing and packaging suggestions"]]],
    ["plan", "30/60/90-day plan", false, [["plan.weeks", "Weekly actions and owners"]]],
  ];
  return defs.map(([key, title, ready, secs]) => {
    const docs = sections.filter((s) => s.stage === key);
    const status: Stage["status"] = !docs.length
      ? "not_started"
      : docs.some((d) => d.status === "needs_refresh")
        ? "needs_refresh"
        : docs.length === secs.length && docs.every((d) => d.status === "confirmed")
          ? "confirmed"
          : "in_progress";
    return { key, title, ready, optional: key === "pricing", status, sections: secs.map(([k, t]) => ({ key: k, title: t, hint: "" })) };
  });
}

const workspace = (): Workspace => ({
  id: WS_ID,
  product_name: "Northwind Payroll (sample)",
  website_url: "https://northwind.example/",
  current_stage: "brief",
  crawl: { status: "done", pages: sources.length },
  pending_ask: pendingAsk,
  busy: false,
  created_at: now,
  updated_at: now,
});

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const demoApi = {
  signup: async () => ({ token: "demo", user }),
  login: async () => ({ token: "demo", user }),
  me: async () => user,
  listWorkspaces: async () => [workspace()],
  createWorkspace: async () => workspace(),
  deleteWorkspace: async () => undefined,
  workspace: async (): Promise<WorkspaceDetail> => ({ workspace: workspace(), stages: stages(), sections }),
  transcript: async () => transcript,
  sources: async () => sources,
  addContext: async (_id: string, title: string): Promise<Source> => {
    const s = { source_id: `s-${Date.now()}`, kind: "paste", url: null, title, page_type: "user_context" };
    sources.push(s);
    return s;
  },
  editSection: async (_id: string, key: string, body_md: string) => {
    sections = sections.map((s) => (s.key === key ? { ...s, body_md, status: "confirmed", user_edited: true, updated_by: "user", version: s.version + 1 } : s));
    return { section: sections.find((s) => s.key === key)!, flagged: [] as string[] };
  },
  confirmSection: async (_id: string, key: string) => {
    sections = sections.map((s) => (s.key === key ? { ...s, status: "confirmed" } : s));
    return sections.find((s) => s.key === key)!;
  },
  exportMarkdown: async () =>
    `# GTM Strategy: Northwind Payroll (sample)\n\n` +
    sections.map((s) => `### ${s.title}\n_Confidence: ${s.confidence} · ${s.status}_\n\n${s.body_md}\n`).join("\n"),
};

/** Simulated agent turn: confirms the section being asked about and moves to the next draft. */
export async function demoStreamChat(_ws: string, body: { text?: string; answers?: AnswerMap }, onEvent: (e: AgentEvent) => void) {
  const asked = pendingAsk;
  const answerText = body.answers ? Object.values(body.answers).map((x) => [...x.selected, x.text].filter(Boolean).join("; ")).join("\n") : body.text ?? "";
  transcript = [...transcript, { role: "user", kind: body.answers ? "answer" : "text", seq: Date.now(), text: answerText }];
  pendingAsk = null;
  await delay(400);
  onEvent({ type: "tool", name: "update_strategy", status: "start", label: "Updating the strategy" });
  await delay(500);

  let reply = "This is demo mode, so I can't reply for real. Connect the backend to talk to the agent.";
  if (asked?.section_key) {
    const key = asked.section_key;
    sections = sections.map((s) => (s.key === key ? { ...s, status: "confirmed" } : s));
    const confirmed = sections.find((s) => s.key === key)!;
    onEvent({ type: "section", section: confirmed });
    const next = sections.find((s) => s.stage === "brief" && s.status === "draft");
    reply = `Thanks, **${confirmed.title}** is confirmed.` + (next ? ` Next: **${next.title}**.` : " The brief is complete; next up is your Ideal Customer Profile.");
    if (next) {
      pendingAsk = {
        intro: `Section: **${next.title}** (${next.confidence} confidence).`,
        questions: [{ id: "ok", text: next.body_md.split("\n")[0].replace(/^[-*]\s*/, ""), options: ["Looks right (suggested)", "Needs a correction"], allow_free_text: true, multi_select: false }],
        section_key: next.key,
      };
    }
  }
  for (const word of reply.split(/(?<= )/)) {
    onEvent({ type: "text", text: word });
    await delay(25);
  }
  transcript = [...transcript, { role: "assistant", kind: "text", seq: Date.now(), text: reply }];
  if (pendingAsk) {
    transcript = [...transcript, { role: "assistant", kind: "ask", seq: Date.now(), ask: pendingAsk }];
    onEvent({ type: "ask", ask: pendingAsk });
  }
  onEvent({ type: "done" });
}
