"""Render self-contained, accessible ER-B HTML without a server or assets."""

# Long inline HTML, JavaScript, and CSS literals are intentional in this static renderer.
# ruff: noqa: E501

from __future__ import annotations

import html
import json
from collections.abc import Iterable
from typing import Any

from riskon.demo.models import DashboardView, StoryView

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; "
    "font-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none';"
)


def render_index_html(
    stories: Iterable[StoryView],
    dashboard: DashboardView,
    presentation_copy: dict[str, Any],
) -> str:
    """Render the complete story, dashboard-summary, and architecture page."""

    story_list = list(stories)
    title = _text(presentation_copy, "title", "RiskON Orchestra")
    return _document(
        title,
        _header(presentation_copy)
        + _tabs(presentation_copy)
        + '<main id="main-content">'
        + '<section id="stories-panel" class="tab-panel" role="tabpanel" aria-labelledby="stories-tab">'
        + '<div class="section-heading"><p class="eyebrow">01 / LIVE PRODUCT STORIES</p>'
        + "<h2>Decisions that show their work</h2>"
        + "<p>Five synthetic stories make the evidence gate, routing boundary, and governed evolution visible.</p></div>"
        + '<div class="story-grid">'
        + "".join(_story_card(story) for story in story_list)
        + "</div></section>"
        + '<section id="dashboard-panel" class="tab-panel" role="tabpanel" aria-labelledby="dashboard-tab" hidden>'
        + '<div class="section-heading"><p class="eyebrow">02 / EVALUATION DASHBOARD</p>'
        + "<h2>Trust is a measured outcome</h2>"
        + "<p>The numbers below are sourced from the frozen evaluator documents and live local runs.</p></div>"
        + _metrics_grid(dashboard)
        + _decision_matrix(dashboard)
        + _safety_grid(dashboard)
        + "</section>"
        + '<section id="architecture-panel" class="tab-panel" role="tabpanel" aria-labelledby="architecture-tab" hidden>'
        + '<div class="section-heading"><p class="eyebrow">03 / ARCHITECTURE &amp; GOVERNANCE</p>'
        + "<h2>Evidence over consensus</h2>"
        + "<p>The runtime scales investigation to risk, while the evidence constitution controls what can be released.</p></div>"
        + _principles(presentation_copy)
        + _architecture(presentation_copy)
        + "</section></main>"
        + _footer(presentation_copy)
        + _tab_script()
        + _embedded_json(
            "riskon-index-data",
            {"stories": [story.model_dump(mode="json") for story in story_list]},
        ),
    )


def render_dashboard_html(
    dashboard: DashboardView,
    presentation_copy: dict[str, Any],
) -> str:
    """Render the dashboard as a standalone file:// document."""

    return _document(
        "RiskON Orchestra — Evaluation Dashboard",
        _header(presentation_copy)
        + '<main id="main-content" class="dashboard-page">'
        + '<div class="section-heading"><p class="eyebrow">EVALUATION DASHBOARD</p>'
        + "<h2>Measured behavior, visible limitations</h2>"
        + "<p>Every ratio and count below carries its evaluator source. Unmeasured values are never invented.</p></div>"
        + _metrics_grid(dashboard)
        + _decision_matrix(dashboard)
        + _safety_grid(dashboard)
        + "</main>"
        + _footer(presentation_copy)
        + _embedded_json("riskon-dashboard-data", dashboard.model_dump(mode="json")),
    )


def render_story_html(story: StoryView, presentation_copy: dict[str, Any]) -> str:
    """Render one story as a standalone demo-case file."""

    return _document(
        f"RiskON Orchestra — {story.title}",
        _header(presentation_copy)
        + '<main id="main-content" class="single-story-page">'
        + '<div class="section-heading"><p class="eyebrow">LIVE PRODUCT STORY</p>'
        + f"<h2>{_e(story.title)}</h2>"
        + f'<p class="story-source">{_e(story.case_id)} · source {_e(story.source_case_id)}</p></div>'
        + _story_card(story, expanded=True)
        + "</main>"
        + _footer(presentation_copy)
        + _embedded_json("riskon-story-data", story.model_dump(mode="json")),
    )


def _document(title: str, body: str) -> str:
    """Wrap trusted template fragments in the static security boundary."""

    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        f"<title>{_e(title)}</title>\n"
        f"<style>{_style()}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _header(copy: dict[str, Any]) -> str:
    """Render the exact local-demo header and status chips."""

    chips = "".join(
        f'<span class="status-chip">{_e(str(item))}</span>' for item in copy["status_chips"]
    )
    return (
        '<header class="site-header">'
        '<div class="header-inner">'
        '<div class="brand-lockup">'
        f'<p class="eyebrow">LOCAL / EVIDENCE-FIRST</p><h1>{_e(str(copy["title"]))}</h1>'
        f'<p class="tagline">{_e(str(copy["tagline"]))}</p>'
        f'<p class="subcopy">{_e(str(copy["subcopy"]))}</p>'
        "</div>"
        f'<div class="status-card" aria-label="Demo status">{chips}</div>'
        "</div></header>"
    )


def _tabs(copy: dict[str, Any]) -> str:
    """Render keyboard-operable tab navigation."""

    section_ids = ("stories", "dashboard", "architecture")
    buttons = []
    for index, (section_id, label) in enumerate(zip(section_ids, copy["sections"], strict=True)):
        selected = index == 0
        buttons.append(
            f'<button class="tab-button" id="{section_id}-tab" role="tab" '
            f'aria-selected="{"true" if selected else "false"}" aria-controls="{section_id}-panel" '
            f'tabindex="{"0" if selected else "-1"}">{_e(str(label))}</button>'
        )
    return (
        '<nav class="tabs" role="tablist" aria-label="Demo sections">' + "".join(buttons) + "</nav>"
    )


def _story_card(story: StoryView, *, expanded: bool = False) -> str:
    """Render the shared story-card layout while hiding empty sections."""

    decision_class = story.decision.casefold()
    context = _key_value_list(story.detected_context)
    evidence = ""
    if story.evidence:
        evidence = (
            '<section class="story-section"><h4>Evidence</h4><div class="evidence-list">'
            + "".join(_evidence_card(item) for item in story.evidence)
            + "</div></section>"
        )
    answer_block = ""
    if story.answer:
        answer_block = (
            f'<div class="answer-box"><strong>Answer</strong><p>{_e(story.answer)}</p></div>'
        )
    elif story.clarifying_question:
        answer_block = f'<div class="clarify-box"><strong>Clarifying question</strong><p>{_e(story.clarifying_question)}</p></div>'
    elif story.abstention_reason:
        answer_block = f'<div class="abstain-box"><strong>Abstention reason</strong><p>{_e(story.abstention_reason)}</p></div>'
    route = _route_section(story.route, story.case_capsule_id)
    counterfactuals = _counterfactual_section(story)
    governance = _governance_section(story)
    trace = _trace_section(story)
    card_class = "story-card story-card-expanded" if expanded else "story-card"
    return (
        f'<article class="{card_class}" data-decision="{_e(decision_class)}">'
        '<div class="story-card-top">'
        f'<span class="story-id">{_e(story.case_id)}</span>'
        f'<span class="decision-badge {_e(decision_class)}">Decision: {_e(story.decision)}</span>'
        "</div>"
        f"<h3>{_e(story.title)}</h3>"
        f'<p class="story-kind">{_e(story.story_kind)} · activation {_e(story.activation_profile)}</p>'
        '<section class="story-section"><h4>Question</h4>'
        f'<p class="question">{_e(story.question)}</p></section>'
        + (
            f'<section class="story-section"><h4>Detected context</h4>{context}</section>'
            if context
            else ""
        )
        + '<section class="story-section"><h4>Decision</h4>'
        + f'<p><span class="decision-badge {decision_class}">{_e(story.decision)}</span> '
        + f"Runtime profile: <strong>{_e(story.runtime_activation_profile)}</strong></p></section>"
        + answer_block
        + evidence
        + f'<section class="story-section"><h4>Why this decision</h4><p>{_e(story.why)}</p></section>'
        + trace
        + counterfactuals
        + route
        + governance
        + f'<section class="story-section audit-ref"><h4>Audit reference</h4><code>{_e(story.audit_reference)}</code></section>'
        + "</article>"
    )


def _evidence_card(item: Any) -> str:
    """Render a redacted evidence card."""

    scope = _key_value_list(item.scope)
    return (
        '<article class="evidence-card">'
        f"<h5>{_e(item.source_title)}</h5>"
        f'<p class="evidence-heading">{_e(item.section_heading)}</p>'
        f'<p class="evidence-meta">{_e(item.criticality)} · {_e(item.provenance_ref)}</p>'
        + (f'<p class="evidence-scope"><strong>Scope:</strong> {scope}</p>' if scope else "")
        + f'<p class="excerpt">{_e(item.excerpt)}</p>'
        + "</article>"
    )


def _trace_section(story: StoryView) -> str:
    """Render the structured trace, never an agent transcript."""

    if not story.orchestra_activity:
        return ""
    items = "".join(
        f'<li><span class="trace-stage">{_e(step.stage)}</span>'
        f"<strong>{_e(step.actor)}</strong><span>{_e(step.detail)}</span></li>"
        for step in story.orchestra_activity
    )
    return f'<section class="story-section"><h4>Orchestra activity</h4><ol class="trace">{items}</ol></section>'


def _counterfactual_section(story: StoryView) -> str:
    """Render visible context transitions if the runtime performed them."""

    if not story.counterfactuals:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{_e(item.dimension)}</td>"
        f"<td>{_e(item.before or 'removed')}</td>"
        f"<td>{_e(item.after or 'removed')}</td>"
        f"<td>{_e(item.decision)}</td>"
        f'<td><span class="pass-label">{"PASS" if item.passed else "FAIL"}</span></td>'
        "</tr>"
        for item in story.counterfactuals
    )
    return (
        '<section class="story-section"><h4>Counterfactual checks</h4>'
        "<table><caption>Context changes and resulting decisions</caption><thead><tr>"
        "<th>Dimension</th><th>Before</th><th>After</th><th>Decision</th><th>Status</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _route_section(route: Any, case_capsule_id: str | None = None) -> str:
    """Render functional routing without real contact details."""

    if route is None:
        return ""
    values = {
        "Support function": route.support_function,
        "Route mode": route.route_mode,
        "Queue / synthetic expert": route.queue_id or route.selected_expert_id or "Not assigned",
        "Case Capsule": (f"created ({case_capsule_id})" if case_capsule_id else "not created"),
        "Routing reason": route.routing_reason,
        "Routing confidence": f"{route.routing_confidence:.2f}",
        "Confidence kind": route.confidence_kind,
    }
    return (
        '<section class="story-section"><h4>Expert route</h4>'
        f'<div class="route-card">{_key_value_list(values)}</div></section>'
    )


def _governance_section(story: StoryView) -> str:
    """Render the M5B lifecycle only for the governed-evolution story."""

    if story.governance is None:
        return ""
    checks = story.governance.checks
    check_rows = (
        (
            "Policy CI",
            f"{checks.policy_ci['matched']}/{checks.policy_ci['expected']} mandatory checks PASS",
        ),
        ("Regression gate", f"{checks.regression['matched']}/{checks.regression['expected']}"),
        (
            "Counterfactual containment",
            f"{checks.counterfactual_containment['matched']}/{checks.counterfactual_containment['expected']}",
        ),
        ("Automatic approval", "yes" if checks.automatic_approval else "no"),
        ("Automatic activation", "yes" if checks.automatic_activation else "no"),
        ("Human approval", "yes" if checks.human_approval else "no"),
        ("Release activation", "yes" if checks.release_activation else "no"),
    )
    lifecycle = (
        "<li>" + "</li><li>".join(_e(stage) for stage in story.governance.lifecycle) + "</li>"
    )
    checks_html = "".join(
        f"<tr><th>{_e(label)}</th><td>{_e(value)}</td></tr>" for label, value in check_rows
    )
    after = _key_value_list(story.governance.after)
    return (
        '<section class="story-section governance-section"><h4>Governance lifecycle</h4>'
        f'<div class="lifecycle"><ol>{lifecycle}</ol></div>'
        f'<div class="governance-grid"><div><h5>Before</h5>{_before_view(story.governance.before)}</div>'
        f"<div><h5>Observed controls</h5><table>{checks_html}</table></div>"
        f'<div><h5>After</h5>{after}<p class="evidence-meta">Patch: {_e(story.governance.patch_status)} · Release: {_e(story.governance.active_release or "none")}</p></div></div>'
        "</section>"
    )


def _before_view(before: Any) -> str:
    """Render the pre-patch decision and optional route."""

    values = {
        "Decision": before.decision,
        "Reason": ", ".join(before.reason_codes),
        "Expert route": "shown" if before.route_present else "none",
    }
    return _key_value_list(values)


def _metrics_grid(dashboard: DashboardView) -> str:
    """Render dashboard metric cards from the dashboard payload."""

    cards = "".join(
        f'<article class="metric-card {_e(metric.status.casefold())}">'
        f'<p class="metric-label">{_e(metric.label)}</p><p class="metric-value">{_e(metric.value)}</p>'
        f'<p class="metric-status">{_e(metric.status)}</p><p class="metric-source">Source: {_e(metric.source)}</p></article>'
        for metric in dashboard.metrics
    )
    return f'<div class="metric-grid">{cards}</div>'


def _decision_matrix(dashboard: DashboardView) -> str:
    """Render expected-vs-actual decision cells with case IDs."""

    by_pair = {(cell.expected, cell.actual): cell for cell in dashboard.decision_matrix.cells}
    header = "".join(
        f'<th scope="col">{_e(label)}</th>' for label in dashboard.decision_matrix.labels
    )
    rows = []
    for expected in dashboard.decision_matrix.labels:
        cells = []
        for actual in dashboard.decision_matrix.labels:
            cell = by_pair[(expected, actual)]
            ids = ", ".join(cell.case_ids) if cell.case_ids else "—"
            cells.append(f"<td><strong>{cell.count}</strong><span>{_e(ids)}</span></td>")
        rows.append(f'<tr><th scope="row">{_e(expected)}</th>{"".join(cells)}</tr>')
    return (
        '<section class="dashboard-section"><div class="section-heading compact"><p class="eyebrow">DECISION MATRIX</p>'
        "<h3>Expected vs actual final decision</h3>"
        f"<p>Source: {_e(dashboard.decision_matrix.source)}</p></div>"
        f'<div class="table-wrap"><table><caption>Rows are expected decisions; columns are actual decisions.</caption>'
        f'<thead><tr><th scope="col">Expected / Actual</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def _safety_grid(dashboard: DashboardView) -> str:
    """Render safety metrics and explicit measurement limits."""

    cards = "".join(
        f'<article class="safety-card {_e(metric.status.casefold())}">'
        f'<p class="metric-label">{_e(metric.label)}</p><p class="metric-value small">{_e(metric.value)}</p>'
        f'<p class="metric-status">{_e(metric.status)}</p><p class="metric-source">Source: {_e(metric.source)}</p></article>'
        for metric in dashboard.safety_metrics
    )
    return (
        '<section class="dashboard-section"><div class="section-heading compact"><p class="eyebrow">SAFETY METRICS</p>'
        '<h3>Guardrails and honest limits</h3></div><div class="safety-grid">'
        f"{cards}</div></section>"
    )


def _principles(copy: dict[str, Any]) -> str:
    """Render the four architecture principles."""

    items = "".join(f"<li>{_e(str(item))}</li>" for item in copy["principles"])
    return f'<ul class="principles">{items}</ul>'


def _architecture(copy: dict[str, Any]) -> str:
    """Render the fixed architecture flow with one sentence per node."""

    nodes = []
    for index, item in enumerate(copy["architecture"]):
        if index:
            nodes.append('<span class="flow-arrow" aria-hidden="true">→</span>')
        nodes.append(
            f'<article class="architecture-node"><h3>{_e(str(item["node"]))}</h3>'
            f"<p>{_e(str(item['description']))}</p></article>"
        )
    return f'<div class="architecture-flow">{"".join(nodes)}</div>'


def _footer(copy: dict[str, Any]) -> str:
    """Render the required synthetic-data and advice disclaimer."""

    return (
        '<footer class="site-footer">'
        + "".join(f"<p>{_e(str(item))}</p>" for item in copy["footer"])
        + "</footer>"
    )


def _key_value_list(values: dict[str, Any]) -> str:
    """Render a small accessible definition list."""

    rows = []
    for key, value in values.items():
        rows.append(f"<dt>{_e(str(key))}</dt><dd>{_e(str(value))}</dd>")
    return f'<dl class="key-values">{"".join(rows)}</dl>'


def _embedded_json(element_id: str, value: Any) -> str:
    """Embed data with characters escaped against closing-script injection."""

    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    for source, replacement in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        payload = payload.replace(source, replacement)
    return f'<script type="application/json" id="{_e(element_id)}">{payload}</script>'


def _tab_script() -> str:
    """Add only local tab navigation behavior."""

    return (
        "<script>"
        "(function(){const tabs=Array.from(document.querySelectorAll('[role=tab]'));"
        "const panels=Array.from(document.querySelectorAll('[role=tabpanel]'));"
        "function selectTab(tab){tabs.forEach(item=>{const selected=item===tab;item.setAttribute('aria-selected',selected?'true':'false');item.tabIndex=selected?0:-1;});"
        "panels.forEach(panel=>{panel.hidden=panel.id!==tab.getAttribute('aria-controls');});tab.focus();}"
        "tabs.forEach(tab=>{tab.addEventListener('click',()=>selectTab(tab));tab.addEventListener('keydown',event=>{"
        "if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;event.preventDefault();"
        "const index=tabs.indexOf(tab);const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(index+1)%tabs.length:(index-1+tabs.length)%tabs.length;selectTab(tabs[next]);});});})();"
        "</script>"
    )


def _text(mapping: dict[str, Any], key: str, fallback: str) -> str:
    """Read a display string from a contract mapping."""

    value = mapping.get(key, fallback)
    return value if isinstance(value, str) else fallback


def _e(value: Any) -> str:
    """HTML-escape a value for text or attribute contexts."""

    return html.escape(str(value), quote=True)


def _style() -> str:
    """Inline the deliberately small responsive and print stylesheet."""

    return """
:root{--navy:#0d1b2a;--navy-soft:#18324a;--white:#fff;--sand:#f1e6d1;--ink:#17212b;--muted:#607080;--line:#d9e0e5;--green:#16734a;--green-soft:#e5f4eb;--amber:#a46100;--amber-soft:#fff2d6;--red:#a63232;--red-soft:#fde8e8;--shadow:0 18px 50px rgba(13,27,42,.12)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f6f7f8;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:16px;line-height:1.55}button{font:inherit}button:focus-visible,a:focus-visible{outline:3px solid var(--sand);outline-offset:3px}.site-header{background:var(--navy);color:var(--white);padding:52px 24px 46px}.header-inner{max-width:1240px;margin:0 auto;display:flex;gap:40px;justify-content:space-between;align-items:flex-start}.brand-lockup{max-width:760px}.eyebrow{margin:0 0 10px;color:#b8c8d5;font-size:12px;font-weight:800;letter-spacing:.14em}.site-header h1{font-size:clamp(2.2rem,6vw,5.2rem);line-height:.98;margin:0 0 18px;letter-spacing:-.055em}.tagline{font-size:clamp(1.2rem,2.5vw,2rem);line-height:1.15;margin:0 0 14px;color:var(--sand);font-weight:700}.subcopy{max-width:680px;margin:0;color:#dce7ee;font-size:1.08rem}.status-card{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;max-width:260px}.status-chip{border:1px solid #6d879c;border-radius:999px;padding:7px 10px;color:#f6fbff;font-size:11px;font-weight:800;letter-spacing:.08em}.tabs{position:sticky;top:0;z-index:2;background:var(--white);border-bottom:1px solid var(--line);display:flex;gap:4px;padding:10px max(24px,calc((100% - 1240px)/2));overflow:auto}.tab-button{border:0;background:transparent;color:var(--muted);cursor:pointer;border-radius:8px;padding:11px 14px;font-weight:800;white-space:nowrap}.tab-button[aria-selected=true]{background:var(--navy);color:var(--white)}main{max-width:1240px;margin:0 auto;padding:70px 24px 100px}.section-heading{max-width:780px;margin-bottom:28px}.section-heading.compact{margin-bottom:18px}.section-heading h2,.section-heading h3{color:var(--navy);font-size:clamp(1.8rem,4vw,3.1rem);line-height:1.05;letter-spacing:-.035em;margin:0 0 12px}.section-heading h3{font-size:1.65rem}.section-heading p{color:var(--muted);margin:0}.story-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,370px),1fr));gap:22px}.story-card{background:var(--white);border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:var(--shadow)}.story-card-expanded{max-width:900px;margin:0 auto}.story-card-top{display:flex;justify-content:space-between;gap:14px;align-items:center}.story-id,.story-kind,.story-source{color:var(--muted);font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.story-card h3{font-size:1.65rem;line-height:1.1;color:var(--navy);margin:19px 0 5px}.story-kind{margin:0 0 20px}.story-section{border-top:1px solid var(--line);padding-top:17px;margin-top:18px}.story-section h4,.story-section h5{color:var(--navy);font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin:0 0 9px}.question{font-size:1.15rem;font-weight:700;margin:0}.decision-badge{display:inline-flex;align-items:center;border-radius:999px;padding:5px 9px;font-size:11px;letter-spacing:.07em;font-weight:900}.decision-badge.answer{background:var(--green-soft);color:var(--green)}.decision-badge.clarify{background:var(--amber-soft);color:var(--amber)}.decision-badge.abstain{background:var(--red-soft);color:var(--red)}.answer-box,.clarify-box,.abstain-box{border-left:4px solid;padding:14px 16px;border-radius:0 10px 10px 0}.answer-box{border-color:var(--green);background:var(--green-soft)}.clarify-box{border-color:var(--amber);background:var(--amber-soft)}.abstain-box{border-color:var(--red);background:var(--red-soft)}.answer-box p,.clarify-box p,.abstain-box p{margin:3px 0 0}.key-values{display:grid;grid-template-columns:minmax(130px, .7fr) 1fr;gap:7px 15px;margin:0}.key-values dt{color:var(--muted);font-size:.9rem}.key-values dd{margin:0;font-weight:700;overflow-wrap:anywhere}.evidence-list{display:grid;gap:12px}.evidence-card{border:1px solid var(--line);background:#fbfcfc;border-radius:12px;padding:14px}.evidence-card h5{font-size:1rem;letter-spacing:0;text-transform:none;margin:0 0 3px}.evidence-heading,.evidence-meta,.evidence-scope{font-size:.86rem;color:var(--muted);margin:0 0 6px}.excerpt{margin:10px 0 0}.trace{list-style:none;padding:0;margin:0;display:grid;gap:10px}.trace li{display:grid;grid-template-columns:150px minmax(120px, .5fr) 1fr;gap:10px;align-items:start;background:#f7f9fa;border-radius:10px;padding:10px}.trace-stage{color:var(--green);font-size:.8rem;font-weight:900;text-transform:uppercase;letter-spacing:.06em}.trace strong{color:var(--navy)}.pass-label{color:var(--green);font-weight:900;font-size:.8rem}.route-card{border:1px solid #d5c8aa;background:var(--sand);border-radius:12px;padding:15px}.lifecycle ol{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:0}.lifecycle li{background:var(--navy);color:var(--white);border-radius:999px;padding:7px 11px;font-size:.82rem;font-weight:800}.governance-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin-top:17px}.governance-grid>div{border:1px solid var(--line);border-radius:12px;padding:14px}.audit-ref code{font-size:.85rem;overflow-wrap:anywhere}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:25px 0 55px}.metric-card,.safety-card{background:var(--white);border:1px solid var(--line);border-radius:15px;padding:18px;box-shadow:0 10px 25px rgba(13,27,42,.07)}.metric-card.pass,.safety-card.pass{border-top:4px solid var(--green)}.metric-card.attention,.safety-card.attention{border-top:4px solid var(--amber)}.metric-label{font-size:.9rem;font-weight:800;color:var(--navy);margin:0}.metric-value{font-size:2rem;line-height:1;margin:12px 0 6px;font-weight:900;color:var(--navy)}.metric-value.small{font-size:1.25rem;line-height:1.2}.metric-status{font-size:.75rem;font-weight:900;letter-spacing:.08em;margin:0;color:var(--green)}.metric-source{font-size:.74rem;color:var(--muted);margin:11px 0 0;overflow-wrap:anywhere}.dashboard-section{border-top:1px solid var(--line);padding-top:30px;margin-top:35px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;background:var(--white);font-size:.92rem}caption{text-align:left;color:var(--muted);font-size:.86rem;margin-bottom:9px}th,td{border:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}thead th{background:var(--navy);color:var(--white)}tbody th{background:#f0f4f6;color:var(--navy)}td strong{display:block;font-size:1.25rem;color:var(--navy)}td span{display:block;color:var(--muted);font-size:.78rem;overflow-wrap:anywhere}.safety-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}.principles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;list-style:none;padding:0;margin:32px 0 55px}.principles li{background:var(--sand);border-radius:12px;padding:16px;color:var(--navy);font-weight:800}.architecture-flow{display:flex;align-items:stretch;gap:10px;overflow-x:auto;padding:10px 2px 20px}.architecture-node{min-width:190px;max-width:220px;background:var(--white);border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:0 10px 25px rgba(13,27,42,.07)}.architecture-node h3{color:var(--navy);font-size:1rem;line-height:1.1;margin:0 0 8px}.architecture-node p{color:var(--muted);font-size:.87rem;margin:0}.flow-arrow{align-self:center;color:var(--green);font-size:1.8rem;font-weight:900}.site-footer{background:var(--navy);color:#dce7ee;padding:25px 24px;text-align:center}.site-footer p{margin:3px;font-size:.86rem}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:800px){.header-inner{display:block}.status-card{justify-content:flex-start;margin-top:28px}.governance-grid,.principles{grid-template-columns:1fr 1fr}.trace li{grid-template-columns:1fr}.architecture-flow{display:grid;grid-template-columns:1fr}.flow-arrow{transform:rotate(90deg);justify-self:center}}@media(max-width:520px){main{padding:45px 16px 70px}.site-header{padding:38px 16px}.tabs{padding:8px 16px}.governance-grid,.principles{grid-template-columns:1fr}.story-card{padding:18px}.key-values{grid-template-columns:1fr}.key-values dd{margin-bottom:7px}}
@media print{.site-header{color:#000;background:#fff;border-bottom:2px solid #000}.tagline,.subcopy{color:#000}.tabs{display:none}.tab-panel[hidden]{display:block}main{padding:20px}.story-grid{display:block}.story-card,.metric-card,.safety-card{box-shadow:none;break-inside:avoid;margin-bottom:15px}.site-footer{color:#000;background:#fff;border-top:1px solid #000}}
"""
