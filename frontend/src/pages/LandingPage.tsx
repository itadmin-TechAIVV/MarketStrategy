import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import {
  IconArrowRight,
  IconCheck,
  IconChat,
  IconDoc,
  IconGauge,
  IconGlobe,
  IconLink,
  IconRefresh,
  IconRoute,
  IconShield,
  IconSpark,
  IconTarget,
  IconUsers,
} from "../components/Icons";
import Logo, { LogoMark } from "../components/Logo";

const STAGES: { title: string; text: string; live?: boolean }[] = [
  { title: "What I understood", text: "A sourced brief of your product, from your own website.", live: true },
  { title: "Ideal Customer Profile", text: "Firmographics, triggers, budget owner, buying committee.", live: true },
  { title: "Personas", text: "Goals, pains, objections and where each buyer spends time." },
  { title: "True value", text: "Value per persona, quantified where possible. Why now, why you." },
  { title: "Competition", text: "Direct, indirect, and doing nothing. Where you win and lose." },
  { title: "Market sizing", text: "TAM / SAM / SOM ranges with every assumption stated." },
  { title: "Difficulty of approach", text: "Segments ranked easiest-to-win first, with honest reasons." },
  { title: "Channels", text: "Outbound, partners, content, events, paid, ranked by fit." },
  { title: "Messaging", text: "One-liner, pitch, pillars, persona hooks, objection sheet." },
  { title: "30/60/90-day plan", text: "Weekly actions, owners, and the metrics that matter." },
];

const FEATURES = [
  { icon: IconLink, title: "Every claim is sourced", text: "Each statement links to the page it came from, or is marked as yours or as an assumption." },
  { icon: IconGauge, title: "Confidence you can see", text: "High, Medium or Low on every section, so you know where to push back first." },
  { icon: IconChat, title: "A conversation, not a report", text: "Short, sharp questions with smart defaults. Accept in one click, or correct in your own words." },
  { icon: IconDoc, title: "A living strategy document", text: "Sections fill in beside the chat as you go. Edit anything; your words become the source of truth." },
  { icon: IconRefresh, title: "Knows what changed", text: "Edit your ICP and every section that depends on it is flagged for refresh, automatically." },
  { icon: IconShield, title: "Private by organisation", text: "Each team's workspaces, sources and answers are kept separate. Export to Markdown or PDF any time." },
];

export default function LandingPage() {
  const { user } = useAuth();
  const primary = user ? { to: "/app", label: "Open the app" } : { to: "/signup", label: "Start your strategy" };

  return (
    <div className="landing">
      <nav className="l-nav">
        <div className="l-container l-nav-inner">
          <Logo light />
          <div className="l-nav-links">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#stages">Stages</a>
            <a href="#trust">Why trust it</a>
          </div>
          <div className="l-nav-cta">
            {!user && (
              <Link to="/login" className="btn ghost" style={{ color: "rgba(255,255,255,0.85)" }}>
                Log in
              </Link>
            )}
            <Link to={primary.to} className="btn white">
              {user ? "Open app" : "Get started"}
            </Link>
          </div>
        </div>
      </nav>

      <header className="hero">
        <div className="l-container hero-inner">
          <span className="eyebrow-pill">
            <IconSpark size={15} /> Your AI go-to-market strategist
          </span>
          <h1>
            Turn your website into a <span className="grad">go-to-market strategy</span> you can defend.
          </h1>
          <p className="hero-sub">
            Paste your product's URL. The agent reads your site, tells you plainly what it understood, asks only what it
            can't know, and builds your ICP, personas, messaging and 90-day plan with you, one stage at a time.
          </p>
          <div className="hero-ctas">
            <Link to={primary.to} className="btn primary lg">
              {primary.label} <IconArrowRight size={18} />
            </Link>
            <a href="#how" className="btn glass lg">
              See how it works
            </a>
          </div>
          <div className="hero-note">
            <span><IconCheck size={15} /> Every claim sourced</span>
            <span><IconCheck size={15} /> Nothing invented</span>
            <span><IconCheck size={15} /> You stay in control</span>
          </div>
        </div>
        <div className="l-container preview-wrap">
          <ProductPreview />
        </div>
      </header>

      <section id="how" className="l-section">
        <div className="l-container">
          <div className="l-head">
            <span className="l-kicker">How it works</span>
            <h2>From a URL to a strategy in one guided conversation</h2>
            <p>No templates to fill in. The agent does the reading; you make the calls.</p>
          </div>
          <div className="steps">
            <div className="step">
              <div className="step-num">1</div>
              <h3>Paste your website</h3>
              <p>The agent reads your home page and up to 25 key pages: pricing, product, customers, use cases and more.</p>
            </div>
            <div className="step">
              <div className="step-num">2</div>
              <h3>Confirm what it understood</h3>
              <p>A brief with sources and confidence for every section. Confirm or correct it, one section at a time.</p>
            </div>
            <div className="step">
              <div className="step-num">3</div>
              <h3>Build the strategy, stage by stage</h3>
              <p>Sharp questions with smart defaults turn into an ICP, personas, messaging and a 30/60/90-day plan.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="l-section alt">
        <div className="l-container">
          <div className="l-head">
            <span className="l-kicker">Features</span>
            <h2>Built for founders and sales leads who need to be right</h2>
          </div>
          <div className="features">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="feature">
                <div className="feature-icon"><Icon size={20} /></div>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="stages" className="l-section">
        <div className="l-container">
          <div className="l-head">
            <span className="l-kicker">The strategy</span>
            <h2>Ten stages, each building on the last</h2>
            <p>Start with what your website already says. Finish with a plan your team can run on Monday.</p>
          </div>
          <div className="stage-track">
            {STAGES.map((s, i) => (
              <div key={s.title} className={`stage-card ${s.live ? "live" : ""}`}>
                <span className="n">{String(i + 1).padStart(2, "0")}</span>
                <h4>{s.title}</h4>
                <p>{s.text}</p>
                {s.live ? <span className="chip green" style={{ justifySelf: "start" }}><span className="dot" />Available</span> : <span className="chip gray" style={{ justifySelf: "start" }}>Coming soon</span>}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="trust" className="l-section alt">
        <div className="l-container trust">
          <div>
            <span className="l-kicker">Why trust it</span>
            <h2 style={{ marginTop: "0.8rem" }}>It tells you where every word came from</h2>
            <p className="muted">
              Strategy built on invented facts is worse than none. So the agent never makes up customers, numbers or
              claims. Anything it infers is labelled as an assumption, and it asks you about it.
            </p>
            <div className="trust-list">
              <div><IconTarget size={20} /><span><strong>Honest about difficulty.</strong> If a segment is hard to reach, it says so and explains why.</span></div>
              <div><IconUsers size={20} /><span><strong>You are the source of truth.</strong> Your corrections override the website, everywhere.</span></div>
              <div><IconRoute size={20} /><span><strong>Leave and come back.</strong> The workspace remembers every answer and picks up where you left off.</span></div>
            </div>
          </div>
          <div className="claim-demo">
            <strong>Pricing model</strong>
            <div className="claim-row">
              <span className="prov website">Website</span>
              <span>Per seat, two tiers, annual discount<small><IconGlobe size={12} /> yourproduct.com/pricing</small></span>
            </div>
            <div className="claim-row">
              <span className="prov user">You</span>
              <span>Enterprise deals are custom-priced<small>Your correction, 2 min ago</small></span>
            </div>
            <div className="claim-row">
              <span className="prov assumption">Assumption</span>
              <span>Most revenue likely comes from the higher tier<small>Agent will ask you to confirm</small></span>
            </div>
          </div>
        </div>
      </section>

      <section className="l-section">
        <div className="l-container">
          <div className="cta-band">
            <LogoMark size={44} />
            <h2>Know how to sell it before you sell it</h2>
            <p>Your strategy feeds straight into lead capture and your CRM, so the whole team works from the same plan.</p>
            <Link to={primary.to} className="btn white lg">
              {primary.label} <IconArrowRight size={18} />
            </Link>
          </div>
        </div>
      </section>

      <footer className="l-footer">
        <div className="l-container l-footer-inner">
          <Logo />
          <span>© {new Date().getFullYear()} GTM Strategy Agent</span>
        </div>
      </footer>
    </div>
  );
}

function ProductPreview() {
  return (
    <div className="preview" aria-hidden="true">
      <div className="pv-bar">
        <i /><i /><i />
        <span className="pv-url">app / strategy / your-product</span>
      </div>
      <div className="pv-body">
        <div className="pv-side">
          <div className="pv-new"><span style={{ color: "var(--v-600)" }}>＋</span> New strategy</div>
          <div className="pv-label">Strategies</div>
          <div className="pv-item on">Your product</div>
          <div className="pv-item">Enterprise add-on</div>
          <div className="pv-item">EU launch</div>
        </div>
        <div className="pv-chat">
          <div className="pv-msg-user">Study our website and tell me what you understood.</div>
          <div className="pv-msg-ai">
            <LogoMark size={22} />
            <div>
              I read <b>14 pages</b> and drafted your brief. Strongest evidence: pricing and features. Biggest gap: which
              regions you sell in.
            </div>
          </div>
          <div className="pv-msg-ai">
            <LogoMark size={22} />
            <div className="pv-ask">
              <b>Who is the main buyer?</b>
              <div className="pv-opts">
                <span className="on">Head of Sales (suggested)</span>
                <span>Founder</span>
                <span>RevOps</span>
              </div>
            </div>
          </div>
        </div>
        <div className="pv-doc">
          <span className="doc-eyebrow">GTM Strategy</span>
          <h4>Your product</h4>
          <div className="pv-steps">
            <span className="done">Brief ✓</span>
            <span className="on">ICP</span>
            <span>Personas</span>
            <span>Value</span>
            <span>Messaging</span>
          </div>
          <div className="pv-sec">
            <div className="pv-sec-head">The product <span className="chip green">Confirmed</span></div>
            <div className="pv-line" style={{ width: "92%" }} />
            <div className="pv-line" style={{ width: "76%" }} />
            <div><span className="prov website">Website 3</span> <span className="prov user">You 1</span></div>
          </div>
          <div className="pv-sec draft">
            <div className="pv-sec-head">Firmographics <span className="chip violet">Draft</span></div>
            <div className="pv-line" style={{ width: "84%" }} />
            <div className="pv-line" style={{ width: "62%" }} />
            <div className="pv-line" style={{ width: "70%" }} />
          </div>
          <div className="pv-sec draft">
            <div className="pv-sec-head">Buying triggers <span className="chip amber">Medium</span></div>
            <div className="pv-line" style={{ width: "88%" }} />
            <div className="pv-line" style={{ width: "55%" }} />
          </div>
        </div>
      </div>
    </div>
  );
}
