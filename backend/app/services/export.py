"""Render the GTM Strategy document as Markdown, with sources per section."""
from __future__ import annotations

from ..agent.stages import STAGES

PROV_LABEL = {"website": "From the website", "user": "From you", "assumption": "Agent assumption"}


def render_markdown(workspace: dict, sections: list[dict], sources: list[dict], statuses: dict[str, str]) -> str:
    by_key = {s["key"]: s for s in sections}
    src = {s["_id"]: s for s in sources}
    lines = [
        f"# GTM Strategy: {workspace['product_name']}",
        "",
        f"Website: {workspace['website_url']}",
        "",
    ]
    for st in STAGES:
        present = [by_key[s.key] for s in st.sections if s.key in by_key]
        if not present:
            continue
        lines += [f"## {st.title}", f"_Stage status: {statuses.get(st.key, '').replace('_', ' ')}_", ""]
        for sec in present:
            badge = f"Confidence: {sec['confidence']} · Status: {sec['status'].replace('_', ' ')}"
            lines += [f"### {sec['title']}", f"_{badge}_", "", sec["body_md"], ""]
            if sec.get("claims"):
                lines.append("<details><summary>Sources</summary>\n")
                for c in sec["claims"]:
                    refs = []
                    for sid in c.get("source_ids", []):
                        s = src.get(sid)
                        if s and s.get("url"):
                            refs.append(f"[{s.get('title') or s['url']}]({s['url']})")
                        elif s:
                            refs.append(s.get("title") or sid)
                    ref_txt = f" ({', '.join(refs)})" if refs else ""
                    lines.append(f"- **{PROV_LABEL.get(c['provenance'], c['provenance'])}:** {c['text']}{ref_txt}")
                lines.append("\n</details>\n")
    return "\n".join(lines).rstrip() + "\n"
