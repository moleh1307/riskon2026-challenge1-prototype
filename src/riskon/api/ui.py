"""Minimal local RiskON evidence-desk interface."""

from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="application-name" content="RiskON Assistant">
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none';
      style-src 'unsafe-inline';
      script-src 'unsafe-inline';
      connect-src 'self';
      base-uri 'none';
      form-action 'self'">
  <title>RiskON / Evidence Desk</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1e211e;
      --muted: #6f736d;
      --faint: #9b9f98;
      --paper: #f5f5f1;
      --card: #fbfbf8;
      --line: #d9dcd4;
      --line-strong: #bfc4bb;
      --accent: #254f42;
      --accent-soft: #e4ece6;
      --warn: #744d24;
      --warn-soft: #f4ecdf;
      --danger: #7c3835;
      --danger-soft: #f3e5e3;
      --max: 1180px;
    }

    * { box-sizing: border-box; }

    html { min-width: 320px; background: var(--paper); }

    body {
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
        sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    button, textarea, select { font: inherit; }

    button { color: inherit; }

    .page {
      width: min(calc(100% - 48px), var(--max));
      min-height: 100svh;
      margin: 0 auto;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    .topbar {
      min-height: 76px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 1px solid var(--line);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 13px;
    }

    .mark {
      width: 30px;
      height: 30px;
      display: grid;
      place-items: center;
      border: 1px solid var(--ink);
      border-radius: 50%;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 17px;
      line-height: 1;
    }

    .brand-name,
    .eyebrow,
    .status,
    .section-label,
    .decision,
    .meta-label,
    .source-label,
    .route-label,
    .input-label {
      text-transform: uppercase;
      letter-spacing: .13em;
      font-size: 10px;
      font-weight: 700;
    }

    .brand-name { letter-spacing: .18em; }

    .brand-sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }

    .top-actions {
      display: flex;
      align-items: center;
      gap: 18px;
    }

    .status {
      display: flex;
      align-items: center;
      gap: 7px;
      color: var(--muted);
      letter-spacing: .09em;
      white-space: nowrap;
    }

    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent);
    }

    .status-dot.offline { background: var(--danger); }

    .new-chat {
      border: 0;
      border-left: 1px solid var(--line);
      padding: 7px 0 7px 18px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
    }

    .new-chat:hover { color: var(--ink); }

    .memory-link {
      padding: 7px 0;
      color: var(--muted);
      font-size: 12px;
      text-decoration: none;
    }

    .memory-link:hover,
    .memory-link:focus-visible { color: var(--ink); }

    .data-settings { position: relative; }

    .data-settings > summary {
      padding: 7px 0;
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
      list-style: none;
      white-space: nowrap;
    }

    .data-settings > summary::-webkit-details-marker { display: none; }

    .data-settings > summary:hover,
    .data-settings > summary:focus-visible { color: var(--ink); }

    .data-panel {
      position: absolute;
      z-index: 10;
      top: calc(100% + 14px);
      right: 0;
      width: min(420px, calc(100vw - 32px));
      padding: 18px;
      border: 1px solid var(--line-strong);
      background: var(--card);
      box-shadow: 0 12px 30px rgba(30, 33, 30, .12);
    }

    .data-panel-title {
      margin: 0 0 6px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 22px;
      font-weight: 400;
      letter-spacing: -.03em;
    }

    .data-panel-copy {
      margin: 0 0 15px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }

    .data-field { display: block; margin-top: 11px; }

    .data-field span {
      display: block;
      margin-bottom: 6px;
      color: var(--faint);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .1em;
      text-transform: uppercase;
    }

    .data-input {
      width: 100%;
      height: 32px;
      padding: 0 8px;
      border: 1px solid var(--line-strong);
      border-radius: 2px;
      outline: 0;
      background: var(--paper);
      color: var(--ink);
      font-size: 12px;
    }

    .data-input:focus { border-color: var(--accent); }

    .data-panel-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 16px;
    }

    .data-save {
      height: 32px;
      padding: 0 12px;
      border: 1px solid var(--ink);
      border-radius: 2px;
      background: var(--ink);
      color: #fff;
      cursor: pointer;
      font-size: 11px;
    }

    .data-save:disabled { cursor: wait; opacity: .55; }

    .data-status {
      color: var(--accent);
      font-size: 11px;
      line-height: 1.4;
    }

    .data-status.error { color: var(--danger); }

    main {
      display: flex;
      flex-direction: column;
      min-height: 0;
      overflow-y: auto;
    }

    .page:not(.has-thread) main {
      justify-content: center;
      padding: 56px 0 72px;
    }

    .empty-state {
      width: 100%;
      display: flex;
      justify-content: center;
    }

    .eyebrow,
    .section-label,
    .input-label { color: var(--accent); }

    h1 {
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(48px, 7vw, 86px);
      font-weight: 400;
      letter-spacing: -.055em;
      line-height: .92;
    }

    .suggestions {
      width: min(100%, 560px);
      border-top: 1px solid var(--ink);
    }

    .suggestions-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 13px 0 15px;
    }

    .suggestions-count {
      color: var(--faint);
      font-size: 11px;
    }

    .suggestion {
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 17px 0;
      border: 0;
      border-top: 1px solid var(--line);
      background: transparent;
      text-align: left;
      cursor: pointer;
      font-size: 13px;
      line-height: 1.35;
    }

    .suggestion::after {
      content: "↗";
      color: var(--faint);
      font-size: 18px;
      transition: transform .18s ease, color .18s ease;
    }

    .suggestion:hover::after {
      color: var(--accent);
      transform: translate(2px, -2px);
    }

    .thread {
      width: 100%;
      align-self: start;
      display: none;
      padding-top: 58px;
    }

    .thread.visible { display: block; }

    .thread-intro {
      max-width: 760px;
      margin-bottom: 46px;
    }

    .thread-title {
      margin: 16px 0 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(38px, 5vw, 64px);
      font-weight: 400;
      letter-spacing: -.045em;
      line-height: .98;
    }

    .turn {
      padding: 24px 0;
      border-top: 1px solid var(--line);
    }

    .question-line {
      display: flex;
      gap: 18px;
      align-items: baseline;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }

    .question-prefix {
      min-width: 54px;
      color: var(--faint);
      text-transform: uppercase;
      letter-spacing: .12em;
      font-size: 10px;
      font-weight: 700;
    }

    .result {
      margin: 22px 0 0 72px;
      padding: 22px 24px 24px;
      border: 1px solid var(--line-strong);
      border-left: 3px solid var(--accent);
      background: var(--card);
    }

    .result[data-decision="CLARIFY"] {
      border-left-color: var(--warn);
      background: var(--warn-soft);
    }

    .result[data-decision="ABSTAIN"] {
      border-left-color: var(--danger);
      background: var(--danger-soft);
    }

    .result-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding-bottom: 17px;
      border-bottom: 1px solid var(--line);
    }

    .decision { color: var(--accent); }

    [data-decision="CLARIFY"] .decision { color: var(--warn); }
    [data-decision="ABSTAIN"] .decision { color: var(--danger); }

    .answer {
      margin: 21px 0 24px;
      white-space: pre-wrap;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 20px;
      line-height: 1.45;
    }

    .secondary {
      margin: -10px 0 23px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }

    .result-footer {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(180px, .65fr);
      gap: 25px;
      padding-top: 17px;
      border-top: 1px solid var(--line);
    }

    .source-label,
    .route-label,
    .meta-label {
      display: block;
      margin-bottom: 9px;
      color: var(--faint);
    }

    .source-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 13px;
      color: var(--accent);
      font-size: 12px;
      line-height: 1.45;
    }

    .source-list span { overflow-wrap: anywhere; }

    .route {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .feedback {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      margin-top: 20px;
      padding-top: 15px;
      border-top: 1px solid var(--line);
      color: var(--faint);
      font-size: 11px;
    }

    .feedback-actions {
      display: flex;
      gap: 6px;
    }

    .feedback-button {
      min-width: 34px;
      height: 28px;
      padding: 0 9px;
      border: 1px solid var(--line-strong);
      border-radius: 2px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
    }

    .feedback-button:hover,
    .feedback-button:focus-visible,
    .feedback-button.selected {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--accent);
    }

    .feedback-status {
      color: var(--accent);
      font-size: 11px;
    }

    .feedback-note-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      margin-top: 10px;
    }

    .feedback-note {
      min-width: 0;
      flex: 1;
      height: 30px;
      padding: 0 8px;
      border: 1px solid var(--line-strong);
      border-radius: 2px;
      outline: 0;
      background: var(--card);
      color: var(--ink);
      font-size: 12px;
    }

    .feedback-note:focus { border-color: var(--accent); }

    .feedback-submit {
      height: 30px;
      padding: 0 10px;
      border: 1px solid var(--ink);
      border-radius: 2px;
      background: var(--ink);
      color: #fff;
      cursor: pointer;
      font-size: 11px;
    }

    .composer-wrap {
      width: 100%;
      flex: 0 0 auto;
      padding: 17px 0 22px;
      border-top: 1px solid var(--ink);
    }

    .page:not(.has-thread) .composer-wrap {
      width: min(100%, 780px);
      margin: 0 auto;
      padding: 0;
      border-top: 0;
    }

    .page:not(.has-thread) .composer {
      padding-top: 20px;
      border-top: 1px solid var(--ink);
    }

    .page:not(.has-thread) textarea {
      min-height: 70px;
      font-size: 18px;
    }

    .composer {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
    }

    .composer-main { min-width: 0; }

    .department-line {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
    }

    .department-line .input-label {
      margin: 0;
      white-space: nowrap;
    }

    .department-note {
      color: var(--faint);
      font-size: 11px;
    }

    .department-select {
      min-width: 170px;
      padding: 5px 22px 5px 0;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      outline: 0;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
    }

    .department-select:focus { border-bottom-color: var(--accent); }

    .input-label {
      display: block;
      margin-bottom: 10px;
    }

    textarea {
      width: 100%;
      min-height: 47px;
      max-height: 160px;
      resize: none;
      padding: 0;
      border: 0;
      outline: 0;
      overflow-y: auto;
      color: var(--ink);
      background: transparent;
      font-size: 15px;
      line-height: 1.5;
    }

    textarea::placeholder { color: var(--faint); }

    .send {
      min-width: 102px;
      height: 42px;
      padding: 0 17px;
      border: 1px solid var(--ink);
      border-radius: 3px;
      background: var(--ink);
      color: #fff;
      cursor: pointer;
      font-size: 12px;
      transition: background .18s ease, color .18s ease;
    }

    .send:hover,
    .send:focus-visible {
      background: var(--accent);
    }

    .send:disabled {
      cursor: wait;
      opacity: .55;
    }

    .composer-foot {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-top: 12px;
      color: var(--faint);
      font-size: 10px;
      line-height: 1.45;
    }

    .ask-progress {
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
    }

    .ask-progress-top {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      line-height: 1.4;
    }

    .progress-dot {
      width: 7px;
      height: 7px;
      flex: 0 0 auto;
      border-radius: 50%;
      background: var(--accent);
      animation: progress-pulse 1.25s ease-in-out infinite;
    }

    .progress-label {
      color: var(--faint);
      font-size: 9px;
      font-weight: 700;
      letter-spacing: .13em;
      text-transform: uppercase;
    }

    .progress-stage { color: var(--accent); }

    .progress-detail {
      margin: 4px 0 0 15px;
      color: var(--faint);
      font-size: 11px;
      line-height: 1.45;
    }

    @keyframes progress-pulse {
      0%, 100% { opacity: .38; transform: scale(.85); }
      50% { opacity: 1; transform: scale(1); }
    }

    .error {
      margin-top: 14px;
      color: var(--danger);
      font-size: 12px;
    }

    @media (max-width: 760px) {
      .page { width: min(calc(100% - 32px), var(--max)); }
      .topbar { min-height: 68px; }
      .brand-sub { display: none; }
      .status { font-size: 9px; }
      .new-chat { padding-left: 13px; }
      .page:not(.has-thread) main { padding: 44px 0 58px; }
      .empty-state { grid-template-columns: 1fr; gap: 55px; }
      .page:not(.has-thread) .composer { grid-template-columns: 1fr; }
      h1 { max-width: 520px; font-size: clamp(46px, 15vw, 70px); }
      .intro-note { margin-top: 30px; }
      .thread-intro { margin-bottom: 32px; }
      .result { margin-left: 0; padding: 19px; }
      .result-footer { grid-template-columns: 1fr; gap: 18px; }
      .feedback { align-items: flex-start; flex-direction: column; gap: 10px; }
    }

    @media (max-width: 480px) {
      .page { width: calc(100% - 26px); }
      .top-actions { gap: 10px; }
      .status { max-width: 96px; white-space: normal; line-height: 1.3; }
      h1 { font-size: 48px; }
      .question-line { display: block; }
      .question-prefix { display: block; margin-bottom: 7px; }
      .composer { grid-template-columns: 1fr; gap: 12px; }
      .send { width: 100%; }
      .composer-foot { display: block; }
      .department-line { align-items: flex-start; flex-wrap: wrap; }
      .department-select { min-width: 150px; }
    }
  </style>
</head>
<body>
  <div class="page">
    <header class="topbar">
      <div class="brand">
        <div class="mark" aria-hidden="true">R</div>
        <div>
          <div class="brand-name">RiskON / Challenge 1</div>
          <div class="brand-sub">Evidence desk · local event runtime</div>
        </div>
      </div>
      <div class="top-actions">
        <div class="status" id="runtimeStatus">
          <span class="status-dot" aria-hidden="true"></span>
          <span>Checking runtime</span>
        </div>
        <details class="data-settings" id="dataSettings">
          <summary>Set local data ↗</summary>
          <div class="data-panel">
            <h2 class="data-panel-title">Connect event data</h2>
            <p class="data-panel-copy">
              Paste the local pages folder and the summary workbook. They stay on this machine
              and are never committed to GitHub.
            </p>
            <label class="data-field" for="pagesPath">
              <span>Pages folder</span>
              <input
                class="data-input"
                id="pagesPath"
                type="text"
                placeholder="/path/to/raw/pages"
                autocomplete="off">
            </label>
            <label class="data-field" for="manifestPath">
              <span>Summary workbook</span>
              <input
                class="data-input"
                id="manifestPath"
                type="text"
                placeholder="/path/to/5_Summary of pages.xlsx"
                autocomplete="off">
            </label>
            <div class="data-panel-actions">
              <button class="data-save" id="saveData" type="button">Use local data</button>
              <span class="data-status" id="dataStatus" role="status" hidden></span>
            </div>
          </div>
        </details>
        <a class="memory-link" href="/memory">Memory summary ↗</a>
        <a class="memory-link" href="/add-html">Add HTML ↗</a>
        <button class="new-chat" id="newChat" type="button">New question</button>
      </div>
    </header>

    <main>
      <section class="empty-state" id="emptyState" aria-label="Question suggestions">
        <div class="suggestions">
          <div class="suggestions-head">
            <span class="section-label">Try a question</span>
            <span class="suggestions-count">04 examples</span>
          </div>
          <button class="suggestion" type="button">
            What support is available on suitability matters?
          </button>
          <button class="suggestion" type="button">
            Who should handle a complex suitability case?
          </button>
          <button class="suggestion" type="button">
            What does LoD mean in this material?
          </button>
          <button class="suggestion" type="button">
            Which alerts apply during the session?
          </button>
        </div>
      </section>

      <section class="thread" id="thread" aria-live="polite">
        <div class="thread-intro">
          <div class="eyebrow">Evidence desk</div>
          <h1 class="thread-title">Source-led answers,<br>clear limits.</h1>
        </div>
        <div id="turns"></div>
      </section>
      <footer class="composer-wrap">
        <form class="composer" id="askForm">
          <div class="composer-main">
            <div class="department-line">
              <label class="input-label" for="department">Department</label>
              <select class="department-select" id="department" autocomplete="organization-title">
                <option value="">Optional</option>
                <option value="Compliance">Compliance</option>
                <option value="Risk Management">Risk Management</option>
                <option value="Wealth Management">Wealth Management</option>
                <option value="Investment Advisory">Investment Advisory</option>
                <option value="Operations">Operations</option>
                <option value="Technology">Technology</option>
                <option value="Legal">Legal</option>
                <option value="Front Office">Front Office</option>
                <option value="Other">Other</option>
              </select>
              <span class="department-note">helps tailor the explanation</span>
            </div>
            <label class="input-label" for="question">Your question</label>
            <textarea
              id="question"
              rows="1"
              placeholder="Ask something from the event material…"
              autocomplete="off"></textarea>
          </div>
          <button class="send" id="send" type="submit">
            Ask desk <span aria-hidden="true">↗</span>
          </button>
        </form>
      <div class="composer-foot">
        <span>Enter a question · ⌘/Ctrl + Enter to send</span>
      </div>
        <div class="ask-progress" id="askProgress" role="status" aria-live="polite" hidden>
          <div class="ask-progress-top">
            <span class="progress-dot" aria-hidden="true"></span>
            <span class="progress-label">Pipeline</span>
            <span class="progress-stage" id="progressStage"></span>
          </div>
          <div class="progress-detail" id="progressDetail"></div>
        </div>
        <div class="error" id="error" role="alert" hidden></div>
      </footer>
    </main>
  </div>

  <script>
    const page = document.querySelector(".page");
    const emptyState = document.getElementById("emptyState");
    const thread = document.getElementById("thread");
    const turns = document.getElementById("turns");
    const form = document.getElementById("askForm");
    const questionInput = document.getElementById("question");
    const sendButton = document.getElementById("send");
    const errorBox = document.getElementById("error");
    const newChat = document.getElementById("newChat");
    const departmentInput = document.getElementById("department");
    const runtimeStatus = document.getElementById("runtimeStatus");
    const statusDot = runtimeStatus.querySelector(".status-dot");
    const statusText = runtimeStatus.querySelector("span:last-child");
    const dataSettings = document.getElementById("dataSettings");
    const pagesPathInput = document.getElementById("pagesPath");
    const manifestPathInput = document.getElementById("manifestPath");
    const saveDataButton = document.getElementById("saveData");
    const dataStatus = document.getElementById("dataStatus");
    const askProgress = document.getElementById("askProgress");
    const progressStage = document.getElementById("progressStage");
    const progressDetail = document.getElementById("progressDetail");

    const labels = {
      ANSWER: "Answer released",
      CLARIFY: "Clarification needed",
      ABSTAIN: "Route to specialist",
    };

    let conversationId = crypto.randomUUID();
    let progressTimer = null;

    const progressStages = [
      ["Reading the question", "Understanding the question and optional department context."],
      [
        "Searching original pages",
        "Matching relevant Julius Baer pages, sections, and tables.",
      ],
      ["Checking evidence", "Verifying exact source spans, scope, and declared meanings."],
      [
        "Running safety checks",
        "Checking claims against the Answer Firewall and specialist rules.",
      ],
      ["Preparing the response", "Keeping only validated claims and original source references."],
    ];

    function addText(parent, className, value) {
      const node = document.createElement("div");
      node.className = className;
      node.textContent = value || "";
      parent.appendChild(node);
      return node;
    }

    function valueOrEmpty(value) {
      return value === null || value === undefined ? "" : String(value);
    }

    function listValues(value) {
      return Array.isArray(value) ? value.filter(Boolean).map(String) : [];
    }

    function routeSummary(route) {
      if (!route) return "";
      if (typeof route === "string") return route;
      if (typeof route !== "object") return "";
      return [
        route.support_function,
        route.route_mode,
        route.queue_id,
      ].filter(Boolean).join(" · ");
    }

    function setRuntimeStatus(ready) {
      statusDot.classList.toggle("offline", !ready);
      statusText.textContent = ready ? "Local runtime ready" : "Runtime unavailable";
    }

    function showProgressStage(index) {
      const stage = progressStages[index];
      progressStage.textContent = stage[0];
      progressDetail.textContent = stage[1];
    }

    function startProgress() {
      window.clearTimeout(progressTimer);
      let index = 0;
      askProgress.hidden = false;
      showProgressStage(index);

      function advance() {
        if (index >= progressStages.length - 1) return;
        index += 1;
        showProgressStage(index);
        progressTimer = window.setTimeout(advance, index === 1 ? 2600 : 4200);
      }

      progressTimer = window.setTimeout(advance, 900);
    }

    function stopProgress() {
      window.clearTimeout(progressTimer);
      progressTimer = null;
      askProgress.hidden = true;
    }

    function loadSavedDataPaths() {
      try {
        const saved = JSON.parse(localStorage.getItem("riskon-event-paths") || "{}");
        pagesPathInput.value = valueOrEmpty(saved.source_root);
        manifestPathInput.value = valueOrEmpty(saved.manifest);
      } catch (error) {
        // Local path memory is only a convenience; the runtime remains authoritative.
      }
    }

    function showDataStatus(message, isError) {
      dataStatus.textContent = message;
      dataStatus.classList.toggle("error", Boolean(isError));
      dataStatus.hidden = false;
    }

    async function connectLocalData() {
      const sourceRoot = pagesPathInput.value.trim();
      const manifest = manifestPathInput.value.trim();
      if (!sourceRoot || !manifest) {
        showDataStatus("Add both local paths first.", true);
        return;
      }
      saveDataButton.disabled = true;
      showDataStatus("Loading local event data…", false);
      try {
        const response = await fetch("/v1/runtime-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_root: sourceRoot, manifest: manifest }),
        });
        const body = await response.json().catch(function() { return {}; });
        if (!response.ok) {
          throw new Error(valueOrEmpty(body.detail) || "Could not load local data.");
        }
        try {
          localStorage.setItem(
            "riskon-event-paths",
            JSON.stringify({ source_root: sourceRoot, manifest: manifest }),
          );
        } catch (error) {
          // The paths are still active for this server even if browser storage is unavailable.
        }
        showDataStatus("Local data connected.", false);
        dataSettings.removeAttribute("open");
        setRuntimeStatus(true);
      } catch (error) {
        showDataStatus(error.message || "Could not load local data.", true);
      } finally {
        saveDataButton.disabled = false;
      }
    }

    function showThread() {
      page.classList.add("has-thread");
      emptyState.style.display = "none";
      thread.classList.add("visible");
    }

    function resetConversation() {
      turns.replaceChildren();
      page.classList.remove("has-thread");
      thread.classList.remove("visible");
      emptyState.style.display = "";
      errorBox.hidden = true;
      errorBox.textContent = "";
      questionInput.value = "";
      departmentInput.value = "";
      conversationId = crypto.randomUUID();
      questionInput.focus();
    }

    function addTurn(question, res) {
      showThread();

      const turn = document.createElement("article");
      turn.className = "turn";

      const questionLine = document.createElement("div");
      questionLine.className = "question-line";
      addText(questionLine, "question-prefix", "Question");
      addText(questionLine, "question-text", question);
      turn.appendChild(questionLine);

      const decision = valueOrEmpty(res.decision) || "ABSTAIN";
      const resultCard = document.createElement("div");
      resultCard.className = "result";
      resultCard.dataset.decision = decision;

      const resultHeader = document.createElement("div");
      resultHeader.className = "result-header";
      addText(resultHeader, "decision", labels[decision] || decision);
      const duration = Number(res.took_ms);
      addText(
        resultHeader,
        "meta-label",
        Number.isFinite(duration) ? Math.round(duration) + " ms" : "",
      );
      resultCard.appendChild(resultHeader);

      const answer = valueOrEmpty(res.answer);
      const clarification = valueOrEmpty(res.clarification);
      const abstention = valueOrEmpty(res.abstention_reason);
      const primaryText = answer || clarification || abstention || "No releasable result.";
      addText(resultCard, "answer", primaryText);

      const secondary = decision === "ANSWER"
        ? ""
        : valueOrEmpty(res.clarification || res.abstention_reason);
      if (secondary && secondary !== primaryText) {
        addText(resultCard, "secondary", secondary);
      }

      const footer = document.createElement("div");
      footer.className = "result-footer";

      const sources = document.createElement("div");
      addText(sources, "source-label", "Original sources");
      const sourceList = document.createElement("div");
      sourceList.className = "source-list";
      const refs = listValues(res.evidence_refs);
      if (refs.length === 0) {
        addText(sourceList, "", "No source reference released");
      } else {
        refs.forEach(function(ref) { addText(sourceList, "", ref); });
      }
      sources.appendChild(sourceList);
      footer.appendChild(sources);

      const route = document.createElement("div");
      addText(route, "route-label", "Runtime path");
      const routeText = [
        routeSummary(res.route),
        valueOrEmpty(res.activation_profile),
        listValues(res.worker_roles).join(" · "),
      ].filter(Boolean).join(" / ");
      addText(route, "route", routeText || "Firewall");
      footer.appendChild(route);

      resultCard.appendChild(footer);

      const feedback = document.createElement("div");
      feedback.className = "feedback";
      const feedbackPrompt = addText(feedback, "", "Was this useful?");
      const feedbackActions = document.createElement("div");
      feedbackActions.className = "feedback-actions";
      const feedbackStatus = addText(feedback, "feedback-status", "");
      const feedbackButtons = [
        ["up", "↑", "Helpful"],
        ["neutral", "—", "Neutral"],
        ["down", "↓", "Needs work"],
      ];
      let submitted = false;
      feedbackButtons.forEach(function(item) {
        const button = document.createElement("button");
        button.className = "feedback-button";
        button.type = "button";
        button.dataset.rating = item[0];
        button.textContent = item[1];
        button.title = item[2];
        button.setAttribute("aria-label", item[2]);
        button.addEventListener("click", function() {
          if (submitted) return;
          if (item[0] === "down") {
            const noteWrap = document.createElement("div");
            noteWrap.className = "feedback-note-wrap";
            const note = document.createElement("input");
            note.className = "feedback-note";
            note.type = "text";
            note.maxLength = 240;
            note.placeholder = "Optional: what should be clearer?";
            const submit = document.createElement("button");
            submit.className = "feedback-submit";
            submit.type = "button";
            submit.textContent = "Send";
            noteWrap.appendChild(note);
            noteWrap.appendChild(submit);
            feedback.appendChild(noteWrap);
            feedbackPrompt.textContent = "Tell us what to improve, or send without a note.";
            button.disabled = true;
            submit.addEventListener("click", function() {
              submitFeedback(item[0], note.value);
            });
            note.focus();
            return;
          }
          submitFeedback(item[0], "");
        });
        feedbackActions.appendChild(button);
      });
      feedback.appendChild(feedbackActions);

      async function submitFeedback(rating, note) {
        if (submitted) return;
        submitted = true;
        try {
          const response = await fetch("/v1/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              conversation_id: conversationId,
              turn_id: valueOrEmpty(res.turn_id) || crypto.randomUUID(),
              rating: rating,
              department: departmentInput.value || null,
              decision: decision,
              note: note || null,
            }),
          });
          if (!response.ok) throw new Error("feedback request failed");
          feedbackStatus.textContent = "Feedback saved";
          feedbackActions.querySelectorAll("button").forEach(function(item) {
            item.disabled = true;
            if (item.dataset.rating === rating) item.classList.add("selected");
          });
        } catch (error) {
          submitted = false;
          feedbackStatus.textContent = "Could not save feedback";
        }
      }

      resultCard.appendChild(feedback);
      turn.appendChild(resultCard);
      turns.appendChild(turn);
      turn.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    async function ask(question) {
      const response = await fetch("/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          context: {},
          conversation_id: conversationId,
          department: departmentInput.value || null,
        }),
      });
      const body = await response.json().catch(function() { return {}; });
      if (!response.ok) {
        throw new Error(valueOrEmpty(body.detail) || "The local runtime could not answer.");
      }
      return Object.assign({}, body.result || {}, {
        took_ms: body.took_ms,
        turn_id: body.turn_id,
        conversation_id: body.conversation_id,
      });
    }

    async function checkRuntime() {
      try {
        const response = await fetch("/v1/health");
        const body = await response.json();
        setRuntimeStatus(response.ok && body.runtime_loaded === true);
      } catch (error) {
        setRuntimeStatus(false);
      }
    }

    function resizeInput() {
      questionInput.style.height = "auto";
      questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + "px";
    }

    form.addEventListener("submit", async function(event) {
      event.preventDefault();
      const question = questionInput.value.trim();
      if (!question || sendButton.disabled) return;

      errorBox.hidden = true;
      sendButton.disabled = true;
      startProgress();
      sendButton.textContent = "Working…";
      try {
        const result = await ask(question);
        addTurn(question, result);
        questionInput.value = "";
        resizeInput();
      } catch (error) {
        errorBox.textContent = error.message || "Something went wrong.";
        errorBox.hidden = false;
      } finally {
        stopProgress();
        sendButton.disabled = false;
        sendButton.innerHTML = 'Ask desk <span aria-hidden="true">↗</span>';
      }
    });

    document.querySelectorAll(".suggestion").forEach(function(button) {
      button.addEventListener("click", function() {
        questionInput.value = button.textContent.trim();
        resizeInput();
        questionInput.focus();
      });
    });

    questionInput.addEventListener("input", resizeInput);
    questionInput.addEventListener("keydown", function(event) {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        form.requestSubmit();
      }
    });
    newChat.addEventListener("click", resetConversation);
    saveDataButton.addEventListener("click", connectLocalData);
    loadSavedDataPaths();
    checkRuntime();
  </script>
</body>
</html>
"""
