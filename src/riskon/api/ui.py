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

    button, textarea { font: inherit; }

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
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
      gap: clamp(40px, 8vw, 100px);
      align-items: start;
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

    .intro-copy {
      max-width: 470px;
      margin: 19px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.65;
    }

    .intro-note {
      max-width: 470px;
      margin-top: 26px;
      padding-top: 13px;
      border-top: 1px solid var(--line);
      color: var(--faint);
      font-size: 11px;
      line-height: 1.5;
    }

    .suggestions {
      align-self: stretch;
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
        <button class="new-chat" id="newChat" type="button">New question</button>
      </div>
    </header>

    <main>
      <section class="empty-state" id="emptyState" aria-label="Ask the evidence desk">
        <div>
          <div class="eyebrow">Ask the evidence desk</div>
          <p class="intro-copy">
            Ask about the Julius Baer material. Every released answer stays tied
            to an original source, with clear limits when the package is not enough.
          </p>
          <p class="intro-note">
            Deterministic retrieval and the Answer Firewall remain authoritative.
          </p>
        </div>

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
          <div>
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
          <span>Original evidence only</span>
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
    const runtimeStatus = document.getElementById("runtimeStatus");
    const statusDot = runtimeStatus.querySelector(".status-dot");
    const statusText = runtimeStatus.querySelector("span:last-child");

    const labels = {
      ANSWER: "Answer released",
      CLARIFY: "Clarification needed",
      ABSTAIN: "Route to specialist",
    };

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
      turn.appendChild(resultCard);
      turns.appendChild(turn);
      turn.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    async function ask(question) {
      const response = await fetch("/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, context: {} }),
      });
      const body = await response.json().catch(function() { return {}; });
      if (!response.ok) {
        throw new Error(valueOrEmpty(body.detail) || "The local runtime could not answer.");
      }
      return Object.assign({}, body.result || {}, { took_ms: body.took_ms });
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
      sendButton.textContent = "Checking…";
      try {
        const result = await ask(question);
        addTurn(question, result);
        questionInput.value = "";
        resizeInput();
      } catch (error) {
        errorBox.textContent = error.message || "Something went wrong.";
        errorBox.hidden = false;
      } finally {
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
    checkRuntime();
  </script>
</body>
</html>
"""
