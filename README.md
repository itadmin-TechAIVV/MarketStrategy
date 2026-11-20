# GTM Strategy Agent

An AI agent that walks a founder or sales lead through building a go-to-market strategy for one
product. It crawls the product website, writes a sourced "What I understood" brief, confirms it
with the user section by section, then interviews the user stage by stage (ICP first) while a live
strategy document fills in next to the chat.

Sits before **GTM Grow** (lead capture) and **Grow CRM** (pipeline). Later it will push ICP,
personas, segments and messaging into both.

## Stack

| Part | Tech | Deploy |
|---|---|---|
| Backend | Python 3.12, FastAPI, pymongo (async), httpx + trafilatura/BeautifulSoup, `google-genai` SDK | Render (`render.yaml`) |
| Database | MongoDB Atlas, multi-tenant by `organization_id` | Atlas |
| AI | Google Gemini (`gemini-flash-latest` by default), streaming, function calling, Google Search grounding | Gemini API |
| Frontend | React 18 + Vite + TypeScript, violet theme | Vercel (`frontend/vercel.json`) |

## Project layout

```
backend/
  app/
    main.py            FastAPI app, CORS, /healthz
    config.py          settings from env (.env locally, Render env in prod)
    db.py              Mongo client + indexes
    auth.py            signup / login / JWT; the only place tokens are handled
    crawler/           safety (SSRF), robots, prioritize, extract, crawler
    agent/
      stages.py        stage registry + dependency graph (brief, icp ready; rest stubbed)
      prompts.py       system prompt (stable, cached)
      tools.py         crawl_site, fetch_page, read_sources, save_section, ask_user, update_strategy
      loop.py          streaming tool-use loop, append-only history, ask_user pause/resume
    services/          sections (update rules), sources, export (Markdown)
    api/               workspaces, sections, sources, transcript, export, chat (SSE)
  tests/               crawler + section-logic tests (no network, no DB)
  scripts/seed_dev.py  create a dev org + user
frontend/
  src/                 api client + SSE reader, auth, pages, chat + strategy document components
render.yaml            Render blueprint for the backend
.env.example           every backend setting
```

## Data model (MongoDB)

| Collection | Purpose |
|---|---|
| `organizations` | tenant |
| `users` | `organization_id`, email, bcrypt hash, role |
| `workspaces` | one per product: website, `current_stage`, crawl status, `pending_ask`, `pending_notes` |
| `sources` | crawled pages, fetched pages, pasted context: url, page_type, text, `content_hash`, `crawl_run_id` |
| `messages` | agent conversation, append-only, provider-neutral blocks with Gemini thought signatures kept (plus a `display` view for the UI) |
| `strategy_sections` | `key`, `stage`, `body_md`, `claims[{text, provenance, source_ids}]`, `confidence`, `status` (draft / confirmed / needs_refresh), `version` |
| `section_versions` | every previous version of a section |

## How the crawler reads difficult websites

`crawl_site` reads the home page plus up to ~25 priority pages, and falls back in layers so a strategy
can almost always be started:

1. Direct fetch with browser-like headers; one retry on 429/503.
2. Pages that are blocked (403, bot-protection pages), time out, or have almost no text (built by
   JavaScript) are re-read through a rendering reader (`CRAWL_READER_URL`, default `https://r.jina.ai/`;
   free without a key, `JINA_API_KEY` raises its limit; set it empty to turn it off).
3. If the home page can't be reached, `www.`/non-`www` and `http://` variants are tried.
4. If the home page exposes few links, common pages (`/pricing`, `/about`, `/features`, ...) are tried.
5. JSON-LD and Open Graph metadata (product, prices, organisation, FAQ) are added to each page's text.
6. robots.txt rules are obeyed; a 4xx or unreachable robots.txt no longer blocks the whole crawl.

If the site still yields little, the agent uses `research_web` (Gemini + Google Search) and stores the
answer, with its web sources, as a citable source. Every URL is SSRF-checked before it is fetched.

## How the agent behaves

- Every claim has a provenance: **website** (must cite a stored source), **user**, or **assumption**.
  The backend rejects website claims without a valid source and refuses saves that drop a user claim.
- Agent saves are drafts; only the user confirms. Editing a section in the document confirms it as
  the user's version and flags every dependent stage **needs refresh**.
- `ask_user` ends the turn. The question is stored on the workspace, so the user can leave and
  resume; their answers become the tool result on the next turn.
- Pasted context and document edits are passed to the agent as notes on its next turn.
- Stages after ICP are defined (sections, dependencies) but marked "coming soon"; the agent says so.

## Run locally

Prerequisites: Python 3.11+, Node 20+, a MongoDB Atlas cluster (or any MongoDB URI), a Gemini API key (https://aistudio.google.com/apikey).

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy ..\.env.example .env      # then fill in MONGO_URI, JWT_SECRET, GEMINI_API_KEY
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Tests (no network or database needed):

```powershell
.\.venv\Scripts\python -m pytest -q
```

Create users: run `.\create_user.bat` in `backend/` (or double-click it). It asks step by step for
email, name, organisation (new or existing), role and password. One-line forms for scripting:

```powershell
.\.venv\Scripts\python -m scripts.create_user add you@example.com --name "Your Name" --org "Acme Inc."
.\.venv\Scripts\python -m scripts.create_user add teammate@example.com --org-id <org id> --role member
.\.venv\Scripts\python -m scripts.create_user list
```

Or just sign up in the UI.

### Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173, talks to http://localhost:8000 by default
```

### Demo mode (no backend)

```powershell
cd frontend
npm run demo       # http://localhost:5174 — the real UI with fictional sample data ("Northwind Payroll")
```

Demo mode (`VITE_DEMO=true`, see `frontend/.env.demo`) skips login and the API and simulates the
confirm-a-section loop. Set `VITE_DEMO=true` on a Vercel preview to share a clickable design.

## Deploy

### MongoDB Atlas
Create a database user, and under Network Access allow Render's outbound IPs (paid Render plans
list static IPs per region). On Render's free plan you must allow `0.0.0.0/0`; use a strong password.

### Backend on Render
New → Blueprint → point at this repo (uses `render.yaml`), then set `MONGO_URI`,
`GEMINI_API_KEY`, `CORS_ORIGINS` (your Vercel URL) and optionally `CORS_ORIGIN_REGEX`
(Vercel previews). Free instances sleep after ~15 minutes idle and take ~1 minute to wake;
a crawl running during a restart is lost (the UI shows the crawl as failed and the agent can re-run it).

### Frontend on Vercel
Import the repo with **Root Directory = `frontend`**, framework Vite, and set
`VITE_API_URL` to the Render URL. `vercel.json` rewrites routes to `index.html`. The browser
calls Render directly (not through Vercel rewrites) so the chat stream isn't buffered.

## Export
- **Markdown**: "Export Markdown" in the document header (`GET /api/workspaces/{id}/export.md`).
- **PDF**: "Print / PDF" uses the browser's print dialog with a print stylesheet (chat hidden, sources shown).

## Later integration (designed for, not built)
- Section keys (`icp.*`, `personas.*`, `messaging.*`, `difficulty.*`) are stable IDs, so pushing to
  GTM Grow and Grow CRM is a mapper over them.
- Re-crawl on demand: `crawl_site(force=true)` stores a new `crawl_run_id`; `content_hash` per URL
  lets a diff view show what changed.
- Login: swap `app/auth.py`'s `decode_token` for Grow CRM's token check; the tenant model is the same.
