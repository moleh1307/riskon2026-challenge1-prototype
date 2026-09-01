# ruff: noqa: E501
"""Generate the deterministic, self-contained HTML backup replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from riskon.demo.models import DemoBundle
from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.errors import PitchSourceError


def load_demo_bundle(path: Path) -> DemoBundle:
    """Load the frozen ER-B bundle used as the only backup-demo source."""

    if not path.is_file():
        raise PitchSourceError(f"ER-B demo bundle not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return DemoBundle.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise PitchSourceError(f"Invalid ER-B demo bundle: {exc}") from exc


def render_backup_html(catalog: PitchCatalog, bundle: DemoBundle) -> str:
    """Render six replay scenes with no remote assets, requests or server."""

    stories = {story.case_id: story.model_dump(mode="json") for story in bundle.stories}
    scene_payloads: list[dict[str, Any]] = []
    for scene in catalog.backup.scenes:
        if scene.story_id == "DASHBOARD":
            payload: dict[str, Any] = {
                "dashboard": bundle.dashboard.model_dump(mode="json"),
                "security": bundle.security,
            }
        else:
            if scene.story_id not in stories:
                raise PitchSourceError(f"Backup scene references missing story {scene.story_id}")
            payload = {"story": stories[scene.story_id]}
        scene_payloads.append(
            {
                "scene_id": scene.scene_id,
                "title": scene.title,
                "story_id": scene.story_id,
                "required_fields": scene.required_fields,
                "payload": payload,
            }
        )
    serialized = json.dumps(scene_payloads, ensure_ascii=False, sort_keys=True)
    serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _HTML_TEMPLATE.replace("__SCENES__", serialized).replace(
        "__FALLBACK__", json.dumps(catalog.backup.fallback_sentence, ensure_ascii=False)
    )


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="RiskON Orchestra deterministic offline replay">
  <title>RiskON Orchestra — Offline Replay</title>
  <style>
    :root { --navy:#0b1f33; --ink:#17212b; --muted:#5c6b77; --sand:#f2e7d5; --green:#2e8b57; --amber:#d99000; --red:#b84545; --line:#d7dee4; --white:#fff; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:var(--navy); color:var(--ink); font:16px Arial, sans-serif; }
    main { width:min(1180px, calc(100vw - 48px)); margin:24px auto; min-height:calc(100vh - 48px); background:var(--white); display:flex; flex-direction:column; box-shadow:0 18px 60px rgba(0,0,0,.22); }
    header { padding:28px 42px 20px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
    .eyebrow { margin:0 0 8px; color:var(--green); font-size:13px; font-weight:bold; letter-spacing:.12em; text-transform:uppercase; }
    h1 { margin:0; color:var(--navy); font-size:36px; line-height:1.12; }
    .counter { color:var(--muted); font-size:14px; white-space:nowrap; padding-top:8px; }
    #content { flex:1; padding:30px 42px 34px; }
    .lead { max-width:880px; color:var(--muted); font-size:21px; line-height:1.4; margin:0 0 24px; }
    .grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:16px; }
    .panel { border:1px solid var(--line); border-top:5px solid var(--navy); padding:18px; min-height:132px; background:#fbfcfd; }
    .panel.green { border-top-color:var(--green); } .panel.amber { border-top-color:var(--amber); } .panel.red { border-top-color:var(--red); }
    .panel h2 { margin:0 0 8px; font-size:21px; color:var(--navy); } .panel p { margin:0; line-height:1.45; color:var(--muted); }
    .decision { display:inline-block; padding:8px 12px; margin-bottom:16px; color:var(--white); background:var(--green); font-size:18px; font-weight:bold; letter-spacing:.08em; }
    .decision.abstain { background:var(--red); } .decision.clarify { background:var(--amber); }
    .trace { display:flex; flex-wrap:wrap; gap:10px; margin:18px 0 24px; }
    .trace span { border:1px solid var(--line); padding:10px 12px; background:var(--sand); font-weight:bold; }
    .trace span::after { content:'  →'; color:var(--muted); } .trace span:last-child::after { content:''; }
    table { border-collapse:collapse; width:100%; font-size:15px; } th, td { border-bottom:1px solid var(--line); padding:11px 10px; text-align:left; vertical-align:top; } th { color:var(--navy); background:#f3f6f8; }
    .metric-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; } .metric { border-left:4px solid var(--green); padding:14px; background:#f3f6f8; } .metric strong { display:block; font-size:27px; color:var(--navy); } .metric small { color:var(--muted); }
    .note { margin-top:22px; padding:15px 18px; background:var(--sand); line-height:1.45; } .note strong { color:var(--navy); }
    footer { padding:16px 42px 22px; display:flex; justify-content:space-between; gap:20px; border-top:1px solid var(--line); color:var(--muted); font-size:13px; }
    kbd { border:1px solid #aeb8c0; border-bottom-width:2px; border-radius:3px; background:#f7f9fa; padding:2px 6px; color:var(--navy); }
    @media (max-width:760px) { main { width:100%; margin:0; min-height:100vh; } header, #content, footer { padding-left:22px; padding-right:22px; } h1 { font-size:29px; } .grid, .metric-grid { grid-template-columns:1fr; } footer { flex-direction:column; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div><p class="eyebrow">Deterministic offline replay</p><h1 id="scene-title">RiskON Orchestra</h1></div>
      <div class="counter" id="scene-counter">Scene 1 / 6</div>
    </header>
    <section id="content" aria-live="polite"></section>
    <footer><span id="fallback-note"></span><span><kbd>←</kbd> <kbd>→</kbd> <kbd>Space</kbd> advance · <kbd>Home</kbd>/<kbd>End</kbd> jump</span></footer>
  </main>
  <script>
    const scenes = __SCENES__;
    const fallbackSentence = __FALLBACK__;
    let index = 0;
    const content = document.getElementById('content');
    const title = document.getElementById('scene-title');
    const counter = document.getElementById('scene-counter');
    const fallbackNote = document.getElementById('fallback-note');
    function node(tag, text, className) { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; }
    function panel(parent, heading, text, tone) { const el = node('article', undefined, 'panel ' + (tone || '')); el.append(node('h2', heading), node('p', text)); parent.append(el); return el; }
    function story(scene) { return scene.payload.story; }
    function renderSceneOne(scene) { const s=story(scene); const lead=node('p', s.question, 'lead'); content.append(lead); const badge=node('div', s.decision, 'decision'); content.append(badge); const grid=node('div', undefined, 'grid'); panel(grid, 'Activation', s.activation_profile + ' · Agents activated: ' + (s.orchestra_activity.length ? s.orchestra_activity.length : '0'), 'green'); panel(grid, 'Answer', s.answer || 'No answer released.', s.answer ? 'green' : 'red'); panel(grid, 'Evidence', s.evidence.length + ' local evidence item(s)', s.evidence.length ? 'green' : 'amber'); content.append(grid); }
    function renderSceneTwo(scene) { const s=story(scene); content.append(node('p', 'Independent worker perspectives meet at one evidence gate.', 'lead')); const trace=node('div', undefined, 'trace'); s.orchestra_activity.forEach(item => trace.append(node('span', item.actor))); content.append(trace); const grid=node('div', undefined, 'grid'); s.agent_roles.forEach(role => panel(grid, role, 'Bounded discovery role', 'green')); content.append(grid); }
    function renderSceneThree(scene) { const s=story(scene); content.append(node('p', 'Change one business fact at a time; the decision must change only when the evidence says it should.', 'lead')); const table=node('table'); const head=node('tr'); ['Dimension','Before → after','Decision','Passed'].forEach(v=>head.append(node('th',v))); table.append(head); s.counterfactuals.forEach(item => { const row=node('tr'); [item.dimension, (item.before || 'present') + ' → ' + (item.after || 'removed'), item.decision, item.passed ? 'YES' : 'NO'].forEach(v=>row.append(node('td',v))); table.append(row); }); content.append(table); content.append(node('div', 'One unresolved material objection blocks an unsafe answer.', 'note')); }
    function renderSceneFour(scene) { const s=story(scene); content.append(node('p', s.question, 'lead')); const badge=node('div', s.decision, 'decision abstain'); content.append(badge); const grid=node('div', undefined, 'grid'); panel(grid, 'Functional route', s.route ? s.route.support_function : 'No route', 'red'); panel(grid, 'Case capsule', s.case_capsule_id || 'Created for expert handoff', 'amber'); panel(grid, 'Why', s.why, 'amber'); content.append(grid); }
    function renderSceneFive(scene) { const s=story(scene); content.append(node('p', 'An expert resolution is evidence for a proposed change, not an automatic change to authoritative knowledge.', 'lead')); const trace=node('div', undefined, 'trace'); (s.governance ? s.governance.lifecycle : []).forEach(item => trace.append(node('span', item))); content.append(trace); const grid=node('div', undefined, 'grid'); panel(grid, 'Policy CI', '11/11 mandatory checks', 'green'); panel(grid, 'Regression', '45/45 cases', 'green'); panel(grid, 'Approval', 'Separate human approval · no automatic activation', 'amber'); content.append(grid); }
    function renderSceneSix(scene) { const d=scene.payload.dashboard; content.append(node('p', 'Current demonstration: synthetic, local and deterministic.', 'lead')); const grid=node('div', undefined, 'metric-grid'); d.metrics.forEach(metric => { const el=node('div', undefined, 'metric'); el.append(node('strong', metric.value), node('small', metric.label)); grid.append(el); }); content.append(grid); content.append(node('div', 'Network enabled: ' + String(scene.payload.security.network_enabled || false) + ' · External assets: 0 · External requests: 0', 'note')); }
    function render() { const scene=scenes[index]; title.textContent=scene.title; counter.textContent='Scene ' + (index+1) + ' / ' + scenes.length; content.replaceChildren(); if(index===0)renderSceneOne(scene); else if(index===1)renderSceneTwo(scene); else if(index===2)renderSceneThree(scene); else if(index===3)renderSceneFour(scene); else if(index===4)renderSceneFive(scene); else renderSceneSix(scene); fallbackNote.textContent='Offline replay · ' + fallbackSentence; }
    function next() { index=Math.min(index+1, scenes.length-1); render(); } function previous() { index=Math.max(index-1,0); render(); }
    document.addEventListener('keydown', event => { if(event.key==='ArrowRight' || event.code==='Space'){event.preventDefault();next();} else if(event.key==='ArrowLeft'){event.preventDefault();previous();} else if(event.key==='Home'){event.preventDefault();index=0;render();} else if(event.key==='End'){event.preventDefault();index=scenes.length-1;render();} });
    render();
  </script>
</body>
</html>"""
