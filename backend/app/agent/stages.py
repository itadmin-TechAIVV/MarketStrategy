"""The strategy stages, in order, and how they depend on each other.

Every stage follows the same contract: a key, the sections it produces, the
stages it depends on, and interview guidance for the agent. A stage with
`ready=False` is a stub: its sections and dependencies are defined (so the
document layout, dependency flags and later integrations already work), but the
agent will not run its interview yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SectionDef:
    key: str
    title: str
    hint: str = ""


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    depends_on: tuple[str, ...]
    sections: tuple[SectionDef, ...]
    guidance: str
    ready: bool = True
    optional: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


BRIEF = Stage(
    key="brief",
    title="What I understood",
    depends_on=(),
    sections=(
        SectionDef("brief.product", "The product", "One line, then one paragraph."),
        SectionDef("brief.problems", "Problems it solves, and for whom"),
        SectionDef("brief.features", "Core features and capabilities"),
        SectionDef("brief.pricing", "Pricing model", "Only if published; otherwise say so."),
        SectionDef("brief.audience", "Who it seems built for", "Industries, company size, roles."),
        SectionDef("brief.proof", "Proof points", "Customers, logos, metrics, testimonials."),
        SectionDef("brief.positioning", "Positioning and tone of voice"),
        SectionDef("brief.competitors", "Competitors and alternatives", "Mentioned or implied."),
        SectionDef("brief.gaps", "Gaps: what the site does not say"),
    ),
    guidance="""\
1. Call crawl_site (once) unless pages are already stored. Then read_sources for the pages you need.
2. Save ALL nine brief sections with save_section as drafts. Every website claim cites source_ids.
   Give each section a confidence: High (stated plainly on the site), Medium (implied or partial),
   Low (inferred, thin evidence). brief.gaps lists what is missing, as assumption-free statements.
3. In chat, give a short overview (3-5 lines), then confirm sections ONE AT A TIME, in order, with
   ask_user (options like "Looks right" / "Needs a correction"). Show the section's key points in the
   question so the user doesn't have to look elsewhere.
4. On "looks right": update_strategy(confirm_section). On a correction: re-save the section with the
   corrected claims marked provenance "user" (they override the website), then confirm it.
5. When all nine are confirmed, update_strategy(complete_stage, stage="brief") and offer to start the ICP stage.""",
)

ICP = Stage(
    key="icp",
    title="Ideal Customer Profile",
    depends_on=("brief",),
    sections=(
        SectionDef("icp.firmographics", "Firmographics", "Industry, company size, geography, tech stack, maturity."),
        SectionDef("icp.triggers", "Buying triggers", "Events that make them look for a solution now."),
        SectionDef("icp.budget_owner", "Budget owner", "Who signs, and from which budget."),
        SectionDef("icp.buying_committee", "Buying committee", "Champion, decision maker, influencers, blockers."),
    ),
    guidance="""\
1. Ask ONE ask_user call with 4-5 short questions covering firmographics, triggers, budget owner and
   buying committee. Every question has 2-4 multiple-choice options drafted from the confirmed brief;
   put your recommended option first and mark it "(suggested)". Allow free text.
2. From the answers, save the four ICP sections. Answers are provenance "user"; anything you inferred
   from the brief is "website" (cite the brief's sources) or "assumption".
3. Show a compact ICP summary and ask the user to confirm it (one ask_user). Apply corrections as "user"
   claims, then confirm each section and complete_stage("icp").""",
)


def _stub(key: str, title: str, depends_on: tuple[str, ...], sections: list[tuple[str, str, str]], guidance: str,
          optional: bool = False) -> Stage:
    return Stage(
        key=key,
        title=title,
        depends_on=depends_on,
        sections=tuple(SectionDef(k, t, h) for k, t, h in sections),
        guidance=guidance,
        ready=False,
        optional=optional,
    )


STAGES: tuple[Stage, ...] = (
    BRIEF,
    ICP,
    _stub("personas", "Personas", ("icp",), [
        ("personas.list", "Personas", "Role, goals, pains, objections, where they spend time, what they read."),
    ], "3-6 questions: which roles, goals, pains, objections, channels and reading habits per persona."),
    _stub("value", "True value", ("personas",), [
        ("value.per_persona", "Value proposition per persona", "Quantified where possible."),
        ("value.why_now", "Why now", ""),
        ("value.why_us", "Why us vs. the status quo", ""),
    ], "Value per persona (time saved, revenue gained, risk reduced), why now, why us vs. status quo."),
    _stub("competition", "Competition and alternatives", ("brief", "icp"), [
        ("competition.landscape", "Direct, indirect, and do-nothing", ""),
        ("competition.edge", "Where we win and where we lose", ""),
    ], "Direct and indirect competitors, doing nothing; our edge and where we lose."),
    _stub("sizing", "Market sizing", ("icp",), [
        ("sizing.tam_sam_som", "TAM / SAM / SOM", "Ranges with stated assumptions; no invented precision."),
    ], "TAM/SAM/SOM as ranges with every assumption stated."),
    _stub("difficulty", "Difficulty of approach", ("icp", "personas", "competition"), [
        ("difficulty.scores", "Segment difficulty scores", "Access, cycle, deal size, DMs, procurement, switching."),
        ("difficulty.where_to_start", "Where to start", "Ranked, easiest to win first, with reasons."),
    ], "Score each segment on access, sales cycle, deal size, decision makers, procurement friction, switching cost."),
    _stub("channels", "Channels", ("icp", "personas", "difficulty"), [
        ("channels.ranked", "Channels ranked by fit", ""),
    ], "Rank outbound, partners, content/SEO, events, paid and marketplaces for this ICP and our resources."),
    _stub("messaging", "Messaging", ("personas", "value", "competition"), [
        ("messaging.core", "One-liner, elevator pitch, three pillars", ""),
        ("messaging.hooks", "Persona hooks", ""),
        ("messaging.objections", "Objection handling", ""),
    ], "One-liner, elevator pitch, three pillars, persona hooks, objection-handling sheet."),
    _stub("pricing", "Pricing and packaging", ("value", "competition"), [
        ("pricing.suggestions", "Pricing and packaging suggestions", ""),
    ], "Only if the user wants it.", optional=True),
    _stub("plan", "30/60/90-day plan", ("difficulty", "channels", "messaging"), [
        ("plan.weeks", "Weekly actions and owners", ""),
        ("plan.metrics", "Metrics that matter", "Leads, meetings, pipeline value, win rate."),
    ], "Weekly actions, owners and metrics for 30/60/90 days."),
)

STAGE_BY_KEY: dict[str, Stage] = {s.key: s for s in STAGES}
SECTION_DEFS: dict[str, tuple[Stage, SectionDef]] = {sec.key: (st, sec) for st in STAGES for sec in st.sections}


def stage_of(section_key: str) -> str:
    if section_key not in SECTION_DEFS:
        raise KeyError(section_key)
    return SECTION_DEFS[section_key][0].key


def downstream_stages(stage_key: str) -> list[str]:
    """All stages that depend (directly or transitively) on `stage_key`, in stage order."""
    affected: set[str] = set()
    changed = True
    while changed:
        changed = False
        for st in STAGES:
            if st.key in affected or st.key == stage_key:
                continue
            if stage_key in st.depends_on or affected.intersection(st.depends_on):
                affected.add(st.key)
                changed = True
    return [st.key for st in STAGES if st.key in affected]


def first_stage() -> Stage:
    return STAGES[0]


def next_stage(stage_key: str) -> Stage | None:
    keys = [s.key for s in STAGES]
    idx = keys.index(stage_key)
    return STAGES[idx + 1] if idx + 1 < len(STAGES) else None
