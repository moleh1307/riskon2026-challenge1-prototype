"""Minimal shared-memory summary for the RiskON assistant."""

from __future__ import annotations

MEMORY_HTML = r"""<!doctype html>
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
  <title>RiskON / Memory summary</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1e211e;
      --muted: #6f736d;
      --faint: #9b9f98;
      --paper: #f5f5f1;
      --line: #d9dcd4;
      --max: 930px;
    }

    * { box-sizing: border-box; }

    html { min-width: 320px; background: var(--paper); }

    body {
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    a { color: inherit; }

    .page {
      width: min(calc(100% - 56px), var(--max));
      min-height: 100svh;
      margin: 0 auto;
    }

    .topbar {
      min-height: 78px;
      display: flex;
      align-items: center;
      gap: 13px;
      border-bottom: 1px solid var(--line);
    }

    .back {
      display: inline-grid;
      width: 28px;
      height: 28px;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--muted);
      font-size: 16px;
      text-decoration: none;
    }

    .back:hover,
    .back:focus-visible { border-color: var(--ink); color: var(--ink); }

    .title {
      font-size: 16px;
      font-weight: 500;
      letter-spacing: -.01em;
    }

    .updated {
      color: var(--faint);
      font-size: 13px;
    }

    .local {
      display: flex;
      align-items: center;
      gap: 7px;
      margin-left: auto;
      color: var(--faint);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .12em;
      text-transform: uppercase;
    }

    .local::before {
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #254f42;
    }

    main { padding: 38px 0 70px; }

    .intro {
      max-width: 800px;
      padding-bottom: 31px;
      border-bottom: 1px solid var(--line);
    }

    .eyebrow {
      margin-bottom: 12px;
      color: var(--faint);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .14em;
      text-transform: uppercase;
    }

    h1 {
      margin: 0 0 14px;
      font-size: clamp(30px, 5vw, 44px);
      font-weight: 500;
      letter-spacing: -.045em;
      line-height: 1.03;
    }

    .intro-copy {
      max-width: 760px;
      margin: 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.6;
    }

    .section { padding-top: 28px; }

    .section h2 {
      margin: 0 0 11px;
      font-size: 23px;
      font-weight: 600;
      letter-spacing: -.025em;
    }

    .section p {
      max-width: 800px;
      margin: 0;
      color: var(--ink);
      font-size: 17px;
      line-height: 1.62;
    }

    .memory-section {
      margin-top: 28px;
      padding-top: 25px;
      border-top: 1px solid var(--line);
    }

    .memory-heading {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 11px;
    }

    .memory-heading h2 { margin: 0; }

    .count {
      color: var(--faint);
      font-size: 12px;
      font-weight: 400;
      white-space: nowrap;
    }

    .memory-item {
      padding: 20px 0 22px;
      border-top: 1px solid var(--line);
    }

    .memory-item:first-child { padding-top: 2px; border-top: 0; }

    .memory-text {
      max-width: 800px;
      margin: 0;
      color: var(--ink);
      font-size: 17px;
      line-height: 1.62;
    }

    .memory-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px 20px;
      margin-top: 10px;
      color: var(--faint);
      font-size: 11px;
    }

    .empty {
      padding: 2px 0 18px;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.6;
    }

    .boundary {
      margin-top: 28px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
      color: var(--faint);
      font-size: 12px;
      line-height: 1.55;
    }

    .error { color: #7c3835; font-size: 13px; }

    @media (max-width: 560px) {
      .page { width: calc(100% - 32px); }
      .topbar { min-height: 68px; }
      .updated { display: none; }
      .local { font-size: 9px; }
      main { padding-top: 30px; }
      .intro-copy, .section p, .memory-text { font-size: 15px; }
    }
  </style>
</head>
<body>
  <div class="page">
    <header class="topbar">
      <a class="back" href="/" aria-label="Back to evidence desk">←</a>
      <span class="title">Memory summary</span>
      <span class="updated" id="updated">Updated just now</span>
      <span class="local">Local only</span>
    </header>

    <main>
      <section class="intro">
        <div class="eyebrow">RiskON / Challenge 1</div>
        <h1>Shared company memory</h1>
        <p class="intro-copy">
          A small, evolving context shared across the assistant. It keeps only durable information
          that can make future answers more useful.
        </p>
      </section>

      <section class="section" aria-labelledby="overviewTitle">
        <h2 id="overviewTitle">Overview</h2>
        <p id="summaryText">Loading memory summary…</p>
      </section>

      <section class="memory-section" aria-labelledby="memoryTitle">
        <div class="memory-heading">
          <h2 id="memoryTitle">Shared memory</h2>
          <span class="count" id="count">—</span>
        </div>
        <div id="items"><div class="empty">Loading…</div></div>
      </section>

      <div class="boundary">
        Memory is context, not evidence. Original Julius Baer sources and the Answer Firewall remain
        the only basis for released answers.
      </div>
      <div class="error" id="error" hidden>Memory is currently unavailable.</div>
    </main>
  </div>

  <script>
    const summaryText = document.getElementById("summaryText");
    const count = document.getElementById("count");
    const items = document.getElementById("items");
    const updated = document.getElementById("updated");
    const errorBox = document.getElementById("error");

    function addText(parent, className, value) {
      const node = document.createElement("div");
      node.className = className || "";
      node.textContent = value || "";
      parent.appendChild(node);
      return node;
    }

    function clear(parent) { parent.replaceChildren(); }

    function formatDate(value) {
      if (!value) return "";
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime())
        ? ""
        : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    }

    async function loadMemory() {
      try {
        const response = await fetch("/v1/memory");
        const body = await response.json().catch(function() { return {}; });
        if (!response.ok) throw new Error("memory unavailable");
        const memoryItems = Array.isArray(body.items) ? body.items : [];
        summaryText.textContent = body.summary || "No durable shared memory has been saved yet.";
        count.textContent = (body.count || 0) + " / " + (body.capacity || "—");
        if (body.updated_at) updated.textContent = "Updated " + formatDate(body.updated_at);
        clear(items);
        if (!memoryItems.length) {
          addText(
            items,
            "empty",
            "No durable shared memory has been saved yet. It will appear here as the assistant "
              "learns reusable context.",
          );
          return;
        }
        memoryItems.forEach(function(item) {
          const article = document.createElement("article");
          article.className = "memory-item";
          addText(article, "memory-text", item.summary);
          const meta = document.createElement("div");
          meta.className = "memory-meta";
          if (Array.isArray(item.departments) && item.departments.length) {
            addText(meta, "", "Shared with · " + item.departments.join(", "));
          }
          const date = formatDate(item.updated_at);
          if (date) addText(meta, "", "Updated · " + date);
          article.appendChild(meta);
          items.appendChild(article);
        });
      } catch (error) {
        errorBox.hidden = false;
        clear(items);
        addText(items, "empty", "The shared memory could not be loaded.");
      }
    }

    loadMemory();
  </script>
</body>
</html>
"""
