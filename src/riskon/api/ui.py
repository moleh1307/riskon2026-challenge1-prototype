"""The RiskON chat UI, served as a self-contained page.

The visual shell is adapted from Gabriel's assistant-v0 branch. It stays as a Python
string because this repository deliberately ignores standalone HTML files. The page talks
only to the canonical event-runtime API and treats its structured response as display data:
the deterministic runtime remains authoritative for every decision and evidence boundary.
"""

# ruff: noqa: E501 - this module is an embedded HTML/CSS/JS asset, not Python to wrap.

from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>RiskON Assistant</title>
<style>
  :root {
    color-scheme: light dark;
    --bg:#f4f5f7; --surface:#fff; --surface-2:#eef0f3; --text:#1b1e24; --muted:#697080;
    --border:#e2e5ea; --accent:#3d5afe; --accent-ink:#fff;
    --answer:#2e7d32; --clarify:#c77700; --route:#3d5afe; --gap:#7b4bd0;
    --answer-bg:#eef7ee; --clarify-bg:#fff6e8; --route-bg:#eef1ff; --gap-bg:#f3eefc;
    --shadow:0 1px 2px rgba(20,24,34,.06), 0 8px 24px rgba(20,24,34,.05);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#14161a; --surface:#1d2025; --surface-2:#23272e; --text:#e8eaed; --muted:#9aa1ab;
      --border:#2e333b; --accent:#6b83ff; --accent-ink:#0e1013;
      --answer:#6ac06e; --clarify:#e0a44a; --route:#6b83ff; --gap:#b18af0;
      --answer-bg:#1a241a; --clarify-bg:#2c2519; --route-bg:#1c2036; --gap-bg:#231c33;
      --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.28);
    }
  }
  * { box-sizing:border-box; }
  html,body { height:100%; }
  body { margin:0; background:var(--bg); color:var(--text);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  .app { display:flex; flex-direction:column; height:100dvh; }

  header { display:flex; align-items:center; gap:12px; padding:14px 20px;
    border-bottom:1px solid var(--border); background:var(--surface); position:sticky; top:0; z-index:5; }
  .logo { width:30px; height:30px; border-radius:8px; background:var(--accent); color:var(--accent-ink);
    display:grid; place-items:center; font-weight:800; flex:none; }
  header h1 { font-size:15px; margin:0; font-weight:650; }
  header p { font-size:12px; margin:1px 0 0; color:var(--muted); }
  header .spacer { flex:1; }
  .ghost { border:1px solid var(--border); background:var(--surface); color:var(--muted);
    font:inherit; font-size:13px; padding:6px 12px; border-radius:8px; cursor:pointer; }
  .ghost:hover { color:var(--text); }

  main { flex:1; overflow-y:auto; }
  .thread { max-width:800px; margin:0 auto; padding:26px 20px 10px; }
  .row { display:flex; margin-bottom:20px; }
  .row.user { justify-content:flex-end; }
  .bubble { background:var(--accent); color:var(--accent-ink); padding:10px 14px;
    border-radius:14px 14px 4px 14px; max-width:80%; white-space:pre-wrap; word-wrap:break-word; }

  .card { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--route);
    border-radius:12px; box-shadow:var(--shadow); padding:16px 18px; width:100%; }
  .card.answer { border-left-color:var(--answer); }
  .card.answer_with_gap { border-left-color:var(--gap); background:var(--gap-bg); }
  .card.clarify { border-left-color:var(--clarify); background:var(--clarify-bg); }
  .card.route { border-left-color:var(--route); background:var(--route-bg); }
  .card.abstain { border-left-color:var(--route); background:var(--route-bg); }

  .pill { display:inline-flex; gap:6px; align-items:center; font-size:11px; font-weight:700;
    letter-spacing:.04em; text-transform:uppercase; margin-bottom:10px; }
  .answer .pill { color:var(--answer); } .clarify .pill { color:var(--clarify); }
  .route .pill { color:var(--route); } .answer_with_gap .pill { color:var(--gap); }
  .abstain .pill { color:var(--route); }
  .dot { width:7px; height:7px; border-radius:50%; background:currentColor; }

  .lead { margin:0 0 10px; }
  .passages { white-space:pre-wrap; word-wrap:break-word; background:var(--surface-2);
    border-radius:10px; padding:12px 14px; font-size:13.5px; max-height:320px; overflow-y:auto; }
  .clarify-q { font-weight:650; margin:10px 0 0; }

  .block { margin-top:14px; border-top:1px dashed var(--border); padding-top:10px; }
  .block > .label { font-size:11px; font-weight:650; color:var(--muted); text-transform:uppercase;
    letter-spacing:.04em; margin-bottom:8px; }
  .src { padding:7px 0; border-bottom:1px solid var(--border); }
  .src:last-child { border-bottom:none; }
  .src a, .src .name { color:var(--text); font-weight:600; font-size:13.5px; text-decoration:none; }
  .src a:hover { color:var(--accent); text-decoration:underline; }
  .src .where { font-size:12px; color:var(--muted); margin-top:2px; }
  .src .snip { font-size:12.5px; color:var(--muted); margin-top:4px;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .expert { padding:6px 0; font-size:13px; }
  .expert .score { color:var(--muted); font-size:12px; }
  .meta { font-size:11.5px; color:var(--muted); margin-top:12px; display:flex; gap:14px; flex-wrap:wrap; }
  .bars { display:flex; gap:14px; margin-top:8px; flex-wrap:wrap; }
  .bar { font-size:11px; color:var(--muted); }
  .bar b { display:block; height:5px; border-radius:3px; background:var(--accent); margin-top:3px; min-width:40px; }

  .empty { max-width:620px; margin:8vh auto 0; text-align:center; padding:0 20px; }
  .empty .logo { width:44px; height:44px; font-size:20px; border-radius:12px; margin:0 auto 16px; }
  .empty h2 { font-size:19px; margin:0 0 6px; }
  .empty p { color:var(--muted); margin:0 0 22px; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
  .chip { border:1px solid var(--border); background:var(--surface); color:var(--text); font:inherit;
    font-size:13px; padding:8px 12px; border-radius:999px; cursor:pointer; text-align:left; }
  .chip:hover { border-color:var(--accent); color:var(--accent); }

  .typing { display:inline-flex; gap:4px; padding:4px 0; }
  .typing i { width:7px; height:7px; border-radius:50%; background:var(--muted); animation:blink 1.3s infinite both; }
  .typing i:nth-child(2){animation-delay:.2s;} .typing i:nth-child(3){animation-delay:.4s;}
  @keyframes blink { 0%,60%,100%{opacity:.25;} 30%{opacity:1;} }

  footer { border-top:1px solid var(--border); background:var(--surface);
    padding:12px 20px calc(12px + env(safe-area-inset-bottom)); position:sticky; bottom:0; }
  .composer { max-width:800px; margin:0 auto; display:flex; gap:10px; align-items:flex-end; }
  .composer textarea { flex:1; resize:none; border:1px solid var(--border); background:var(--bg);
    color:var(--text); font:inherit; padding:11px 14px; border-radius:12px; max-height:160px; line-height:1.5; }
  .composer textarea:focus { outline:2px solid var(--accent); outline-offset:-1px; border-color:transparent; }
  .send { flex:none; width:42px; height:42px; border:none; border-radius:12px; background:var(--accent);
    color:var(--accent-ink); cursor:pointer; display:grid; place-items:center; }
  .send:disabled { opacity:.4; cursor:default; }
  .send svg { width:18px; height:18px; }
  .disclaimer { max-width:800px; margin:8px auto 0; font-size:11px; color:var(--muted); text-align:center; }
  @media (max-width:560px){ .bubble{max-width:88%;} }
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo">R</div>
    <div><h1>RiskON Assistant</h1><p>Evidence-first answers from the event corpus</p></div>
    <div class="spacer"></div>
    <button class="ghost" id="reset">New chat</button>
  </header>
  <main id="main"><div class="thread" id="thread"></div></main>
  <footer>
    <form class="composer" id="composer">
      <textarea id="input" rows="1" placeholder="Ask a policy or compliance question…" autocomplete="off"></textarea>
      <button class="send" id="send" type="submit" aria-label="Send">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
      </button>
    </form>
    <div class="disclaimer">The deterministic Answer Firewall decides what can be released. Evidence references remain local and inspectable.</div>
  </footer>
</div>
<script>
"use strict";

const EXAMPLES = [
  "Is it mandatory for a Power of Attorney holder to have a K&E document?",
  "Can a RM give advice on digital assets to any client?",
  "How can I change the K&E of an existing client?",
  "I am blocked for entering a purchase order in Wealth Navigator, how can I unblock it?",
];

const PILLABEL = {
  ANSWER: "Answer",
  CLARIFY: "Needs clarification",
  ABSTAIN: "Route to a specialist",
};

/* The only place that knows the backend shape: POST /v1/ask -> { took_ms, result }. */
async function ask(question) {
  const res = await fetch("/v1/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, context: {} }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(res.status + " — " + detail);
  }
  return (await res.json()).result;
}

const thread = document.getElementById("thread");
const main = document.getElementById("main");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const send = document.getElementById("send");
let pending = false, started = false;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
}
function down() { main.scrollTop = main.scrollHeight; }

function renderEmpty() {
  thread.innerHTML =
    '<div class="empty"><div class="logo">R</div><h2>What do you need to verify?</h2>' +
    '<p>Ask a Julius Baer policy question. The runtime answers only when the source and scope are established.</p>' +
    '<div class="chips">' +
    EXAMPLES.map(q => '<button class="chip" data-q="' + esc(q) + '">' + esc(q) + "</button>").join("") +
    "</div></div>";
  thread.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => submit(c.dataset.q)));
}

function sources(list, label) {
  if (!list || !list.length) return "";
  const items = list.map(ref =>
    '<div class="src"><span class="name">' + esc(ref) + "</span></div>"
  ).join("");
  return '<div class="block"><div class="label">' + esc(label) + "</div>" + items + "</div>";
}

function routing(r) {
  if (!r) return "";
  const target = r.support_function || r.queue_id || r.selected_expert_id || "configured specialist";
  const mode = r.route_mode ? " · " + esc(r.route_mode) : "";
  return '<div class="block"><div class="label">Route to</div>' +
    "<div><strong>" + esc(target) + "</strong>" + mode + "</div>" +
    (r.routing_reason ? '<div class="where">' + esc(r.routing_reason) + "</div>" : "") +
    (r.routing_confidence != null
      ? '<div class="where">routing confidence ' + Number(r.routing_confidence).toFixed(2) + "</div>"
      : "") +
    "</div>";
}

function confidences(res) {
  const bars = [];
  if (res.route && typeof res.route.routing_confidence === "number") {
    const confidence = res.route.routing_confidence;
    bars.push('<div class="bar">routing confidence ' + confidence.toFixed(2) +
      '<b style="width:' + Math.round(confidence * 120) + 'px"></b></div>');
  }
  return bars.length ? '<div class="bars">' + bars.join("") + "</div>" : "";
}

function reasons(list) {
  if (!list || !list.length) return "";
  return '<div class="block"><div class="label">Why</div>' +
    list.map(item => '<div class="where">• ' + esc(item) + "</div>").join("") + "</div>";
}

function metadata(res) {
  const bits = [];
  if (res.activation_profile) bits.push("profile " + res.activation_profile);
  if (typeof res.worker_execution_count === "number")
    bits.push(res.worker_execution_count + " worker(s)");
  if (res.worker_roles && res.worker_roles.length)
    bits.push("roles " + res.worker_roles.join(", "));
  return bits.length ? '<div class="meta">' + bits.map(esc).join(" · ") + "</div>" : "";
}

function renderResult(res) {
  const row = document.createElement("div");
  row.className = "row assistant";
  const decision = String(res.decision || "ABSTAIN").toUpperCase();
  const cssClass = decision.toLowerCase();
  let body = '<div class="pill"><span class="dot"></span>' +
    esc(PILLABEL[decision] || decision) + "</div>";

  if (decision === "ANSWER") {
    body += '<div class="passages">' + esc(res.answer || "No released answer.") + "</div>";
    body += sources(res.evidence_refs, "Evidence references");
  } else if (decision === "CLARIFY") {
    body += '<p class="lead">More context is needed before the Firewall can release an answer.</p>';
    if (res.clarification) body += '<p class="clarify-q">' + esc(res.clarification) + "</p>";
    body += reasons(res.abstention_reason);
  } else {
    body += '<p class="lead">The runtime could not safely release an answer from the available evidence.</p>';
    body += reasons(res.abstention_reason);
  }

  if (decision === "ABSTAIN") body += routing(res.route);
  body += confidences(res);
  body += metadata(res);

  row.innerHTML = '<div class="card ' + esc(cssClass) + '">' + body + "</div>";
  thread.appendChild(row);
  down();
}

function addUser(text) {
  if (!started) { thread.innerHTML = ""; started = true; }
  const row = document.createElement("div");
  row.className = "row user";
  row.innerHTML = '<div class="bubble">' + esc(text) + "</div>";
  thread.appendChild(row);
  down();
}
function addTyping() {
  const row = document.createElement("div");
  row.className = "row assistant"; row.id = "typing";
  row.innerHTML = '<div class="card"><div class="typing"><i></i><i></i><i></i></div></div>';
  thread.appendChild(row); down();
}
function rmTyping() { const t = document.getElementById("typing"); if (t) t.remove(); }
function addError(msg) {
  const row = document.createElement("div");
  row.className = "row assistant";
  row.innerHTML = '<div class="card route"><div class="pill"><span class="dot"></span>Connection problem</div>' +
    '<p class="lead">Could not reach the assistant: ' + esc(msg) + "</p></div>";
  thread.appendChild(row); down();
}

async function submit(text) {
  text = (text || "").trim();
  if (!text || pending) return;
  addUser(text);
  pending = true; send.disabled = true; addTyping();
  try {
    const res = await ask(text);
    rmTyping(); renderResult(res);
  } catch (e) {
    rmTyping(); addError(e.message || String(e));
  } finally {
    pending = false; send.disabled = false; input.focus();
  }
}

form.addEventListener("submit", e => { e.preventDefault(); const v = input.value; input.value = ""; grow(); submit(v); });
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
function grow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; }
input.addEventListener("input", grow);
document.getElementById("reset").addEventListener("click", () => { started = false; renderEmpty(); input.focus(); });

renderEmpty();
input.focus();
</script>
</body>
</html>
"""
