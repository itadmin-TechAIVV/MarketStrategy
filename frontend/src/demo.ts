// Demo mode (VITE_DEMO=true): the real UI with sample data and no backend.
// All content is fictional and labelled as sample output. No website is read.
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

interface DemoWs {
  ws: Workspace;
  sections: Section[];
  transcript: TranscriptItem[];
  pendingAsk: Ask | null;
  sources: Source[];
  phase: "new" | "brief" | "icp_questions" | "icp_confirm" | "done";
}

const store = new Map<string, DemoWs>();
let demoUser: User = {
  id: "demo-user",
  name: "Alex Morgan",
  email: "alex@demo.example",
  role: "admin",
  organization: { id: "demo-org", name: "Demo Organisation" },
};

const STAGE_DEFS: [string, string, boolean, [string, string][]][] = [
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
const TITLES = Object.fromEntries(STAGE_DEFS.flatMap(([, , , secs]) => secs));

const w = (text: string, ...ids: string[]): Claim => ({ text, provenance: "website", source_ids: ids });
const u = (text: string): Claim => ({ text, provenance: "user", source_ids: [] });
const a = (text: string): Claim => ({ text, provenance: "assumption", source_ids: [] });

function sec(key: string, body_md: string, claims: Claim[], confidence: Section["confidence"], status: Section["status"] = "draft"): Section {
  return {
    id: key, key, stage: key.split(".")[0], title: TITLES[key], body_md, claims, confidence, status,
    version: 1, updated_by: "agent", user_edited: false, refresh_reason: null,
  };
}

function makeSources(base: string, label: string): Source[] {
  const pages: [string, string, string][] = [
    ["", "home", `${label} – Home`], ["pricing", "pricing", "Pricing"], ["features", "features", "Features"],
    ["product", "product", "Product overview"], ["customers", "customers", "Customers"], ["solutions", "solutions", "Solutions"],
    ["about", "about", "About us"], ["compare", "compare", "Compare"],
  ];
  return pages.map(([path, type, title], i) => ({
    source_id: `s${i}`, kind: "crawl", url: `${base}${path}`, title: i ? `${title} – ${label}` : title, page_type: type,
  }));
}

/** Generic, clearly-sample brief for any product name. */
function sampleBrief(name: string): Section[] {
  return [
    sec("brief.product", `**${name} helps mid-sized B2B teams run [core workflow] in one place.** _(sample)_\n\nIt replaces spreadsheets and disconnected tools with a single workspace, automates the repetitive steps, and gives managers a live view of progress.`,
      [w("Single workspace replacing spreadsheets", "s0"), w("Automates repetitive steps", "s3")], "High"),
    sec("brief.problems", "- **Operations leads** lose hours a week stitching data between tools.\n- **Managers** can't see status without chasing people.\n- **Teams** make errors copying data by hand.",
      [w("Hours lost between tools", "s0"), a("Error reduction is implied, not stated")], "Medium"),
    sec("brief.features", "- Workflow builder with templates\n- Integrations with common CRMs and spreadsheets\n- Dashboards and alerts\n- Roles and permissions",
      [w("Workflow builder", "s2"), w("CRM and spreadsheet integrations", "s2"), w("Roles and permissions", "s2")], "High"),
    sec("brief.pricing", "- **Per seat per month**, three tiers (Starter, Growth, Enterprise)\n- Annual discount; Enterprise is quote-based\n- 14-day free trial",
      [w("Three tiers, per seat", "s1"), w("14-day trial", "s1")], "High"),
    sec("brief.audience", "- **Industries:** professional services, SaaS, logistics\n- **Size:** 50–1,000 employees\n- **Roles:** operations lead (user), department head (buyer)",
      [w("Industries named on solutions page", "s5"), a("Company size inferred from logos and tier limits")], "Medium"),
    sec("brief.proof", "- 4 customer stories\n- \"Cut weekly reporting from 6 hours to 30 minutes\" (customer quote)\n- No published customer count or revenue figures",
      [w("Four customer stories", "s4"), w("6 hours to 30 minutes quote", "s4")], "Medium"),
    sec("brief.positioning", "- **Positioning:** the simple alternative to heavyweight enterprise suites\n- **Tone:** confident, practical, light on jargon",
      [w("Simple alternative to enterprise suites", "s0", "s7")], "Medium"),
    sec("brief.competitors", "- **Named:** spreadsheets, legacy enterprise suites\n- **Implied:** point tools for each step\n- **Do nothing:** keep the manual process",
      [w("Compares itself with spreadsheets and suites", "s7"), a("Point tools are the real day-to-day competitors")], "Low"),
    sec("brief.gaps", "- Which regions and languages are supported\n- Implementation time and onboarding model\n- Security certifications (SOC 2, ISO 27001)\n- Typical contract size",
      [a("None of these appear anywhere on the site")], "High"),
  ];
}

function seedNorthwind(): DemoWs {
  const base = "https://northwind.example/";
  const sources = makeSources(base, "Northwind Payroll");
  const sections = sampleBrief("Northwind Payroll").map((s, i) =>
    i < 2 ? { ...s, status: "confirmed" as const } : s,
  );
  sections[0] = { ...sections[0], body_md: "**Payroll and shift-pay software for independent healthcare clinics.** _(sample)_\n\nNorthwind runs payroll for clinics with shift-based staff: it imports rota hours, applies overtime and on-call rules, pays staff, and files payroll taxes." };
  sections[1] = { ...sections[1], claims: [...sections[1].claims, u("Our main buyer is the practice manager, not the owner")] };
  const ask = briefAsk(sections[2], 3);
  return {
    ws: {
      id: "demo-northwind", product_name: "Northwind Payroll", website_url: base, current_stage: "brief",
      crawl: { status: "done", pages: sources.length }, pending_ask: ask, busy: false,
      created_at: new Date(Date.now() - 3600_000).toISOString(), updated_at: new Date(Date.now() - 3600_000).toISOString(),
    },
    sources, sections, pendingAsk: ask, phase: "brief",
    transcript: [
      { role: "user", kind: "text", seq: 1, text: `Please study our website ${base} and tell me what you understood about Northwind Payroll.` },
      { role: "assistant", kind: "text", seq: 2, text: "I read **8 pages** (home, pricing, features, product, customers, solutions, about, compare) and drafted your brief on the right.\n\n- **Strongest evidence:** features and pricing, both stated plainly.\n- **Weakest:** competitors. The site only compares itself with spreadsheets.\n- **Biggest gap:** which countries and payroll tax regimes you support.\n\nLet's confirm it one section at a time." },
      { role: "assistant", kind: "ask", seq: 2, ask: briefAsk(sections[0], 1) },
      { role: "user", kind: "answer", seq: 3, text: "Looks right" },
      { role: "assistant", kind: "ask", seq: 4, ask: briefAsk(sections[1], 2) },
      { role: "user", kind: "answer", seq: 5, text: "Needs a correction; our main buyer is the practice manager, not the owner" },
      { role: "assistant", kind: "text", seq: 6, text: "Got it. I've recorded **the practice manager as the main buyer** as your statement. It overrides the website from now on." },
      { role: "assistant", kind: "ask", seq: 6, ask },
    ],
  };
}

function seedBrightdesk(): DemoWs {
  const base = "https://brightdesk.example/";
  const sections = sampleBrief("Brightdesk").map((s) => ({ ...s, status: "confirmed" as const }));
  const d = new Date(Date.now() - 3 * 86_400_000).toISOString();
  return {
    ws: { id: "demo-brightdesk", product_name: "Brightdesk", website_url: base, current_stage: "icp", crawl: { status: "done", pages: 8 }, pending_ask: null, busy: false, created_at: d, updated_at: d },
    sources: makeSources(base, "Brightdesk"), sections, pendingAsk: null, phase: "icp_questions",
    transcript: [
      { role: "user", kind: "text", seq: 1, text: `Please study our website ${base} and tell me what you understood about Brightdesk.` },
      { role: "assistant", kind: "text", seq: 2, text: "Your brief is fully confirmed. Next up is your **Ideal Customer Profile**. Send any message when you're ready and I'll ask 4 quick questions." },
    ],
  };
}

function ensureSeeded() {
  if (store.size) return;
  for (const d of [seedNorthwind(), seedBrightdesk()]) store.set(d.ws.id, d);
}

function briefAsk(s: Section, n: number): Ask {
  const firstLine = s.body_md.split("\n").find((l) => l.trim())?.replace(/^[-*]\s+/, "").replace(/_\(sample\)_/, "").trim() ?? "";
  return {
    intro: `Section ${n} of 9 · **${s.title}** (${s.confidence} confidence)`,
    questions: [{ id: "ok", text: `${firstLine}${/[.!?*]$/.test(firstLine) ? "" : "."} Is this right?`, options: ["Looks right (suggested)", "Needs a correction"], allow_free_text: true, multi_select: false }],
    section_key: s.key,
  };
}

const ICP_ASK: Ask = {
  intro: "Four quick questions to pin down your **Ideal Customer Profile**. I've pre-selected what your confirmed brief suggests.",
  questions: [
    { id: "size", text: "Which company size should we target first?", options: ["50–250 employees (suggested)", "250–1,000 employees", "1,000+ employees"], allow_free_text: true, multi_select: false },
    { id: "industry", text: "Which industries fit best? Pick all that apply.", options: ["Professional services (suggested)", "SaaS", "Logistics", "Healthcare"], allow_free_text: true, multi_select: true },
    { id: "trigger", text: "What usually makes them start looking?", options: ["Team grows past spreadsheets (suggested)", "New leader joins", "Failed audit or error", "Tool contract renewal"], allow_free_text: true, multi_select: false },
    { id: "budget", text: "Who owns the budget?", options: ["Head of Operations (suggested)", "CFO / Finance", "Department head"], allow_free_text: true, multi_select: false },
  ],
};

function stages(d: DemoWs): Stage[] {
  return STAGE_DEFS.map(([key, title, ready, secs]) => {
    const docs = d.sections.filter((s) => s.stage === key);
    const status: Stage["status"] = !docs.length
      ? "not_started"
      : docs.some((x) => x.status === "needs_refresh")
        ? "needs_refresh"
        : docs.length === secs.length && docs.every((x) => x.status === "confirmed")
          ? "confirmed"
          : "in_progress";
    return { key, title, ready, optional: key === "pricing", status, sections: secs.map(([k, t]) => ({ key: k, title: t, hint: "" })) };
  });
}

function get(id: string): DemoWs {
  ensureSeeded();
  const d = store.get(id);
  if (!d) throw new Error("Workspace not found");
  return d;
}

const touch = (d: DemoWs) => { d.ws.updated_at = new Date().toISOString(); d.ws.pending_ask = d.pendingAsk; };
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const demoApi = {
  signup: async (body: { name: string; email: string; organization_name: string }) => {
    demoUser = { ...demoUser, name: body.name || demoUser.name, email: body.email, organization: { id: "demo-org", name: body.organization_name || "Demo Organisation" } };
    return { token: "demo", user: demoUser };
  },
  login: async (email: string) => {
    demoUser = { ...demoUser, email };
    return { token: "demo", user: demoUser };
  },
  me: async () => demoUser,
  listWorkspaces: async () => {
    ensureSeeded();
    return [...store.values()].map((d) => d.ws).sort((x, y) => y.updated_at.localeCompare(x.updated_at));
  },
  createWorkspace: async (product_name: string, website_url: string) => {
    ensureSeeded();
    const url = website_url.includes("://") ? website_url : `https://${website_url}`;
    const id = `demo-${Date.now()}`;
    const now = new Date().toISOString();
    const d: DemoWs = {
      ws: { id, product_name, website_url: url.endsWith("/") ? url : `${url}/`, current_stage: "brief", crawl: null, pending_ask: null, busy: false, created_at: now, updated_at: now },
      sections: [], transcript: [], pendingAsk: null, sources: [], phase: "new",
    };
    store.set(id, d);
    return d.ws;
  },
  deleteWorkspace: async (id: string) => { store.delete(id); },
  workspace: async (id: string): Promise<WorkspaceDetail> => {
    const d = get(id);
    return { workspace: { ...d.ws, pending_ask: d.pendingAsk }, stages: stages(d), sections: [...d.sections] };
  },
  transcript: async (id: string) => [...get(id).transcript],
  sources: async (id: string) => [...get(id).sources],
  addContext: async (id: string, title: string): Promise<Source> => {
    const s = { source_id: `p${Date.now()}`, kind: "paste", url: null, title, page_type: "user_context" };
    get(id).sources.push(s);
    return s;
  },
  editSection: async (id: string, key: string, body_md: string) => {
    const d = get(id);
    d.sections = d.sections.map((s) => (s.key === key ? { ...s, body_md, status: "confirmed", user_edited: true, updated_by: "user", confidence: "High", version: s.version + 1 } : s));
    return { section: d.sections.find((s) => s.key === key)!, flagged: [] as string[] };
  },
  confirmSection: async (id: string, key: string) => {
    const d = get(id);
    d.sections = d.sections.map((s) => (s.key === key ? { ...s, status: "confirmed" } : s));
    return d.sections.find((s) => s.key === key)!;
  },
  exportMarkdown: async (id: string) => {
    const d = get(id);
    return `# GTM Strategy: ${d.ws.product_name} (demo)\n\n` +
      d.sections.map((s) => `### ${s.title}\n_Confidence: ${s.confidence} · ${s.status}_\n\n${s.body_md}\n`).join("\n");
  },
};

async function say(d: DemoWs, text: string, onEvent: (e: AgentEvent) => void) {
  for (const word of text.split(/(?<= )/)) {
    onEvent({ type: "text", text: word });
    await delay(18);
  }
  onEvent({ type: "block_end" });
  d.transcript.push({ role: "assistant", kind: "text", seq: Date.now(), text });
}

function ask(d: DemoWs, q: Ask, onEvent: (e: AgentEvent) => void) {
  d.pendingAsk = q;
  d.transcript.push({ role: "assistant", kind: "ask", seq: Date.now(), ask: q });
  onEvent({ type: "ask", ask: q });
}

/** Simulated agent turn. */
export async function demoStreamChat(id: string, body: { text?: string; answers?: AnswerMap }, onEvent: (e: AgentEvent) => void) {
  const d = get(id);
  const asked = d.pendingAsk;
  const answerText = body.answers
    ? Object.values(body.answers).map((x) => [...x.selected, x.text].filter(Boolean).join("; ")).join("\n\n")
    : body.text ?? "";
  d.transcript.push({ role: "user", kind: body.answers ? "answer" : "text", seq: Date.now(), text: answerText });
  d.pendingAsk = null;
  await delay(500);

  if (d.phase === "new") {
    // Simulated crawl.
    const host = d.ws.website_url.replace(/^https?:\/\//, "").replace(/\/$/, "");
    d.sources = makeSources(d.ws.website_url, d.ws.product_name);
    onEvent({ type: "tool", name: "crawl_site", status: "start", label: "Reading your website" });
    for (let i = 1; i <= d.sources.length; i++) {
      onEvent({ type: "crawl", status: "running", fetched: i, title: d.sources[i - 1].title });
      await delay(260);
    }
    onEvent({ type: "crawl", status: "done", fetched: d.sources.length });
    onEvent({ type: "sources_changed" });
    onEvent({ type: "tool", name: "read_sources", status: "start", label: "Reading pages" });
    await delay(700);
    onEvent({ type: "tool", name: "save_section", status: "start", label: "Writing your brief" });
    for (const s of sampleBrief(d.ws.product_name)) {
      d.sections.push(s);
      onEvent({ type: "section", section: s });
      await delay(320);
    }
    d.phase = "brief";
    await say(d,
      `_Demo mode: I didn't really read ${host}. This is sample output so you can try the flow._\n\n` +
      `I read **${d.sources.length} pages** and drafted your brief on the right.\n\n` +
      "- **Strongest evidence:** features and pricing, both stated plainly.\n- **Weakest:** competitors (Low confidence).\n- **Biggest gap:** regions, onboarding and security certifications.\n\nLet's confirm it one section at a time.",
      onEvent);
    ask(d, briefAsk(d.sections[0], 1), onEvent);
  } else if (d.phase === "brief" && asked?.section_key) {
    onEvent({ type: "tool", name: "update_strategy", status: "start", label: "Updating the strategy" });
    await delay(450);
    const key = asked.section_key;
    const correction = body.answers?.ok?.text?.trim();
    d.sections = d.sections.map((s) =>
      s.key === key ? { ...s, status: "confirmed", claims: correction ? [...s.claims, u(correction)] : s.claims } : s,
    );
    const done = d.sections.find((s) => s.key === key)!;
    onEvent({ type: "section", section: done });
    const idx = d.sections.findIndex((s) => s.stage === "brief" && s.status !== "confirmed");
    if (idx >= 0) {
      await say(d, correction ? `Noted. **${done.title}** now includes your correction and is confirmed.` : `Thanks, **${done.title}** is confirmed.`, onEvent);
      ask(d, briefAsk(d.sections[idx], idx + 1), onEvent);
    } else {
      d.ws.current_stage = "icp";
      d.phase = "icp_confirm";
      onEvent({ type: "workspace_changed" });
      await say(d, "Your brief is fully confirmed. 🎉 Now let's define your **Ideal Customer Profile**.", onEvent);
      d.phase = "icp_questions";
      ask(d, ICP_ASK, onEvent);
    }
  } else if (d.phase === "icp_questions") {
    if (!asked) {
      await say(d, "Great, let's define your **Ideal Customer Profile**.", onEvent);
      ask(d, ICP_ASK, onEvent);
    } else {
      const pick = (q: string) => body.answers?.[q] ? [...body.answers[q].selected, body.answers[q].text].filter(Boolean).join(", ").replace(/ \(suggested\)/g, "") : "";
      onEvent({ type: "tool", name: "save_section", status: "start", label: "Writing your ICP" });
      await delay(500);
      const icp = [
        sec("icp.firmographics", `- **Size:** ${pick("size")}\n- **Industries:** ${pick("industry")}\n- **Geography:** to confirm (not on the website)`, [u(`Size: ${pick("size")}`), u(`Industries: ${pick("industry")}`), a("Geography unknown")], "Medium"),
        sec("icp.triggers", `- ${pick("trigger")}\n- Secondary: tool contract renewal (assumption)`, [u(pick("trigger")), a("Renewal timing is a common secondary trigger")], "Medium"),
        sec("icp.budget_owner", `- **${pick("budget")}** signs\n- Budget usually from operations tooling`, [u(pick("budget")), a("Budget line inferred")], "Medium"),
        sec("icp.buying_committee", "- **Champion:** operations lead\n- **Decision maker:** budget owner\n- **Influencers:** IT/security, finance\n- **Blocker risk:** IT if SSO is missing", [w("Roles and permissions page targets IT", "s2"), a("Committee shape inferred from deal size")], "Low"),
      ];
      for (const s of icp) {
        d.sections.push(s);
        onEvent({ type: "section", section: s });
        await delay(300);
      }
      d.phase = "icp_confirm";
      await say(d, "Here's your draft **ICP** on the right. The buying committee is the least certain part (Low confidence).", onEvent);
      ask(d, {
        intro: "Does this ICP look right?",
        questions: [{ id: "ok", text: "Confirm all four ICP sections?", options: ["Confirm ICP (suggested)", "I want to change something"], allow_free_text: true, multi_select: false }],
        section_key: "icp",
      }, onEvent);
    }
  } else if (d.phase === "icp_confirm" && asked?.section_key === "icp") {
    d.sections = d.sections.map((s) => (s.stage === "icp" ? { ...s, status: "confirmed" } : s));
    d.sections.filter((s) => s.stage === "icp").forEach((s) => onEvent({ type: "section", section: s }));
    d.phase = "done";
    d.ws.current_stage = "personas";
    onEvent({ type: "workspace_changed" });
    await say(d, "Your **ICP is confirmed**. Personas, value, messaging and the 90-day plan are coming in the next version of this agent.", onEvent);
  } else {
    await say(d, "This is demo mode, so I can't reply to free text. Use the answer cards, or connect the backend to talk to the real agent.", onEvent);
    if (asked) ask(d, asked, onEvent);
  }
  touch(d);
  onEvent({ type: "done" });
}
