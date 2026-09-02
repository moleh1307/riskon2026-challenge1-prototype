"""Local-only HTML intake page for the RiskON demo."""

# The HTML/CSS/JavaScript below is intentionally kept readable as one embedded page.
# ruff: noqa: E501

HTML_INGEST_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'">
  <title>RiskON / Add HTML</title>
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
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    button { color: inherit; font: inherit; }
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
    .brand { display: flex; align-items: center; gap: 13px; }
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
    .brand-name, .eyebrow, .status, .section-label, .meta-label {
      text-transform: uppercase;
      letter-spacing: .13em;
      font-size: 10px;
      font-weight: 700;
    }
    .brand-name { letter-spacing: .18em; }
    .brand-sub { margin-top: 4px; color: var(--muted); font-size: 12px; }
    .top-actions { display: flex; align-items: center; gap: 18px; }
    .status {
      display: flex;
      align-items: center;
      gap: 7px;
      color: var(--muted);
      letter-spacing: .09em;
      white-space: nowrap;
    }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
    .back-link {
      padding: 7px 0 7px 18px;
      border-left: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      text-decoration: none;
    }
    .back-link:hover, .back-link:focus-visible { color: var(--ink); }
    main { padding: 72px 0 88px; }
    .intro { max-width: 680px; margin-bottom: 42px; }
    .eyebrow { color: var(--accent); }
    h1 {
      margin: 14px 0 15px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(44px, 6vw, 76px);
      font-weight: 400;
      letter-spacing: -.055em;
      line-height: .94;
    }
    .intro-copy {
      max-width: 580px;
      margin: 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.55;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(300px, .82fr) minmax(0, 1.18fr);
      gap: 24px;
      align-items: start;
    }
    .panel {
      min-width: 0;
      padding: 24px;
      border: 1px solid var(--line-strong);
      background: var(--card);
    }
    .panel-heading {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }
    .panel-title { margin: 0; font-size: 15px; font-weight: 600; }
    .panel-note { color: var(--faint); font-size: 11px; }
    .dropzone {
      min-height: 250px;
      margin-top: 22px;
      padding: 28px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      border: 1px dashed var(--line-strong);
      background: var(--paper);
      cursor: pointer;
      transition: border-color .18s ease, background .18s ease;
    }
    .dropzone:hover, .dropzone:focus-visible, .dropzone.is-dragging {
      border-color: var(--accent);
      background: var(--accent-soft);
      outline: 0;
    }
    .drop-icon {
      width: 42px;
      height: 42px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line-strong);
      border-radius: 50%;
      color: var(--accent);
      font-size: 22px;
    }
    .drop-title { margin-top: 18px; font-family: Georgia, "Times New Roman", serif; font-size: 24px; }
    .drop-copy { margin-top: 7px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .browse {
      margin-top: 18px;
      padding: 9px 13px;
      border: 1px solid var(--ink);
      border-radius: 2px;
      background: var(--ink);
      color: #fff;
      cursor: pointer;
      font-size: 11px;
    }
    .browse:hover, .browse:focus-visible { background: var(--accent); }
    #fileInput { display: none; }
    .file-info { min-height: 42px; margin-top: 18px; }
    .file-name { overflow-wrap: anywhere; font-size: 13px; font-weight: 600; }
    .file-stats { margin-top: 4px; color: var(--faint); font-size: 11px; }
    .local-note {
      margin: 20px 0 0;
      padding-top: 15px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
      line-height: 1.5;
    }
    .result-panel { min-height: 410px; }
    .empty-result {
      min-height: 320px;
      display: grid;
      place-items: center;
      color: var(--faint);
      text-align: center;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 22px;
    }
    .result-content[hidden] { display: none; }
    .result-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 18px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }
    .result-title { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: 28px; font-weight: 400; line-height: 1.05; }
    .result-status { color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; white-space: nowrap; }
    .metadata-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0 22px;
      margin-top: 20px;
    }
    .metadata-item { min-width: 0; padding: 13px 0; border-top: 1px solid var(--line); }
    .metadata-item.wide { grid-column: 1 / -1; }
    .metadata-value { color: var(--ink); font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }
    .metadata-value.list { color: var(--accent); }
    .metadata-value.boolean { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    .hash-row { margin-top: 9px; color: var(--faint); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; line-height: 1.45; overflow-wrap: anywhere; }
    .json-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 23px; }
    .copy-button {
      padding: 7px 10px;
      border: 1px solid var(--line-strong);
      border-radius: 2px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 11px;
    }
    .copy-button:hover, .copy-button:focus-visible { border-color: var(--accent); color: var(--accent); }
    .json-output {
      max-height: 250px;
      margin: 10px 0 0;
      padding: 14px;
      overflow: auto;
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--muted);
      font: 11px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .error { margin-top: 15px; color: var(--danger); font-size: 12px; line-height: 1.45; }
    @media (max-width: 820px) {
      .page { width: min(calc(100% - 32px), var(--max)); }
      .topbar { min-height: 68px; }
      .brand-sub { display: none; }
      .status { display: none; }
      main { padding: 52px 0 64px; }
      .workspace { grid-template-columns: 1fr; }
    }
    @media (max-width: 480px) {
      .page { width: calc(100% - 26px); }
      .top-actions { gap: 10px; }
      .back-link { padding-left: 11px; }
      .panel { padding: 18px; }
      .dropzone { min-height: 220px; padding: 20px; }
      .metadata-grid { grid-template-columns: 1fr; }
      .result-top { display: block; }
      .result-status { display: block; margin-top: 12px; }
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
          <div class="brand-sub">Source intake · local demo tool</div>
        </div>
      </div>
      <div class="top-actions">
        <div class="status"><span class="status-dot" aria-hidden="true"></span>Local only</div>
        <a class="back-link" href="/">Back to evidence desk ↗</a>
      </div>
    </header>

    <main>
      <section class="intro">
        <div class="eyebrow">Source intake / demo</div>
        <h1>Add an HTML source.</h1>
        <p class="intro-copy">Drop an event page here and get a compact routing metadata card. The file is read in this browser only; it is not uploaded, saved, or used as answer evidence.</p>
      </section>

      <section class="workspace" aria-label="HTML metadata intake">
        <div class="panel">
          <div class="panel-heading">
            <h2 class="panel-title">HTML file</h2>
            <span class="panel-note">.html / .htm</span>
          </div>
          <div class="dropzone" id="dropzone" role="button" tabindex="0" aria-label="Drop an HTML file or choose one">
            <div class="drop-icon" aria-hidden="true">↓</div>
            <div class="drop-title">Drop HTML here</div>
            <div class="drop-copy">or choose a local file<br>up to 8 MB</div>
            <button class="browse" id="browseButton" type="button">Choose file</button>
            <input id="fileInput" type="file" accept=".html,.htm,text/html">
          </div>
          <div class="file-info" id="fileInfo" aria-live="polite">
            <div class="file-name">No source selected</div>
            <div class="file-stats">Metadata will appear on the right.</div>
          </div>
          <p class="local-note">Routing metadata only · original HTML remains the source of truth.</p>
          <div class="error" id="error" role="alert" hidden></div>
        </div>

        <div class="panel result-panel">
          <div class="panel-heading">
            <h2 class="panel-title">Metadata output</h2>
            <span class="panel-note">Page Card shape</span>
          </div>
          <div class="empty-result" id="emptyResult">Your metadata card<br>will appear here.</div>
          <div class="result-content" id="resultContent" hidden>
            <div class="result-top">
              <h2 class="result-title" id="resultTitle">Untitled page</h2>
              <div class="result-status">Local preview</div>
            </div>
            <div class="hash-row" id="hashRow"></div>
            <div class="metadata-grid" id="metadataGrid"></div>
            <div class="json-head">
              <span class="meta-label">JSON output</span>
              <button class="copy-button" id="copyButton" type="button">Copy JSON</button>
            </div>
            <pre class="json-output" id="jsonOutput" aria-label="Metadata JSON"></pre>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const dropzone = document.getElementById("dropzone");
    const browseButton = document.getElementById("browseButton");
    const fileInput = document.getElementById("fileInput");
    const fileInfo = document.getElementById("fileInfo");
    const emptyResult = document.getElementById("emptyResult");
    const resultContent = document.getElementById("resultContent");
    const resultTitle = document.getElementById("resultTitle");
    const hashRow = document.getElementById("hashRow");
    const metadataGrid = document.getElementById("metadataGrid");
    const jsonOutput = document.getElementById("jsonOutput");
    const copyButton = document.getElementById("copyButton");
    const errorBox = document.getElementById("error");
    const MAX_BYTES = 8 * 1024 * 1024;
    let currentJson = "";

    const stopWords = new Set((
      "about after again against all also and are around because before being between " +
      "both but can client could does each for from have into its more most other our " +
      "page should some than that their there these they this through what when where " +
      "which with your the was were will would html http https www content data document " +
      "section information overview support available required using used only into " +
      "not activated"
    ).split(" "));

    const ignoredAcronyms = new Set(["HTML", "HTTP", "HTTPS", "CSS", "JS", "URL", "XML", "UTF", "DOCTYPE"]);
    const scopeTerms = [
      "Advice Premium", "Advice Light", "Advice Exclusive", "Trade Basic", "Discretionary",
      "Advisory", "Switzerland", "BC CH", "CH", "Session", "Overnight", "Active",
      "Solicitation", "Reverse Solicitation", "Client", "Professional", "Retail",
      "Jurisdiction", "Booking Centre", "Booking Center", "Suitability", "Compliance",
      "Knowledge & Experience", "K&E", "DTM", "CPR", "ESG", "MiFID", "SFDR"
    ];

    function clean(value) {
      return String(value || "").replace(/\s+/g, " ").trim();
    }

    function limitWords(value, limit) {
      const words = clean(value).split(" ").filter(Boolean);
      return words.slice(0, limit).join(" ") + (words.length > limit ? "…" : "");
    }

    function textOf(node) {
      return clean(node ? node.textContent : "");
    }

    function escapeRegExp(value) {
      return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function extractTopics(doc, bodyText) {
      const scores = new Map();
      const display = new Map();
      function add(text, weight) {
        const words = clean(text).match(/[A-Za-z][A-Za-z0-9&/-]{2,}/g) || [];
        words.forEach(function(word) {
          const key = word.toLowerCase();
          if (stopWords.has(key) || /^\d+$/.test(key) || key.length < 3) return;
          scores.set(key, (scores.get(key) || 0) + weight);
          if (!display.has(key)) display.set(key, word);
        });
      }
      add(textOf(doc.querySelector("title")), 8);
      Array.from(doc.querySelectorAll("h1, h2, h3")).forEach(function(node) { add(textOf(node), 5); });
      Array.from(doc.querySelectorAll('meta[name="keywords"]')).forEach(function(node) { add(node.getAttribute("content") || "", 6); });
      add(bodyText.slice(0, 100000), 1);
      return Array.from(scores.entries())
        .sort(function(a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); })
        .slice(0, 8)
        .map(function(item) { return display.get(item[0]); });
    }

    function extractAcronyms(sourceText) {
      const matches = sourceText.match(/\b[A-Z][A-Z0-9]*(?:[&/-][A-Z0-9]+)+\b|\b[A-Z]{2,}[0-9]*\b/g) || [];
      return Array.from(new Set(matches.filter(function(item) {
        return item.length <= 16 && !ignoredAcronyms.has(item);
      }))).slice(0, 16);
    }

    function extractScopeTerms(sourceText) {
      const lower = sourceText.toLowerCase();
      return scopeTerms.filter(function(term) {
        const pattern = new RegExp("(^|[^a-z0-9])" + escapeRegExp(term.toLowerCase()) + "($|[^a-z0-9])", "i");
        return pattern.test(lower);
      });
    }

    function iconNodes(container) {
      return Array.from(container.querySelectorAll("*")).filter(function(node) {
        const tag = (node.tagName || "").toLowerCase();
        return tag === "ac:emoticon" || tag === "ac:image";
      });
    }

    function iconState(node) {
      const tag = (node.tagName || "").toLowerCase();
      if (tag === "ac:emoticon") {
        return clean(node.getAttribute("ac:name") || node.getAttribute("name") || "");
      }
      return clean(node.getAttribute("ac:alt") || node.getAttribute("alt") || "image");
    }

    function precedingHeading(node) {
      let sibling = node.previousElementSibling;
      while (sibling) {
        if (/^H[1-6]$/.test(sibling.tagName || "")) return textOf(sibling);
        sibling = sibling.previousElementSibling;
      }
      return "";
    }

    function findLegend(doc) {
      const direct = doc.querySelector(".legend");
      if (direct) return direct;
      const heading = Array.from(doc.querySelectorAll("h1, h2, h3, h4, h5, h6")).find(function(node) {
        return /legend/i.test(textOf(node));
      });
      return heading ? heading.nextElementSibling : null;
    }

    function extractLegend(doc) {
      const root = findLegend(doc);
      const entries = root ? iconNodes(root).map(function(node) {
        return {
          raw_icon: iconState(node),
          declared_meaning: textOf(node.parentElement)
        };
      }).filter(function(entry) { return entry.raw_icon; }) : [];
      return {
        present: entries.length > 0,
        entries: entries
      };
    }

    function extractTableMetadata(doc) {
      return Array.from(doc.querySelectorAll("table")).map(function(table, index) {
        const rows = Array.from(table.querySelectorAll("tr"));
        const headers = Array.from(table.querySelectorAll("th")).map(textOf).filter(Boolean);
        const columnHeaders = Array.from(new Set(headers));
        const dataRows = rows.filter(function(row) { return !row.querySelector("th"); });
        const cells = Array.from(table.querySelectorAll("th, td"));
        const columnCount = rows.reduce(function(max, row) {
          const width = Array.from(row.children).reduce(function(total, cell) {
            return total + Math.max(1, Number(cell.getAttribute("colspan")) || 1);
          }, 0);
          return Math.max(max, width);
        }, 0);
        const mergedCells = cells.filter(function(cell) {
          return Number(cell.getAttribute("rowspan")) > 1 || Number(cell.getAttribute("colspan")) > 1;
        });
        const iconStates = Array.from(new Set(iconNodes(table).map(iconState).filter(Boolean)));
        return {
          index: index + 1,
          heading: precedingHeading(table),
          matrix: dataRows.length > 1 && columnHeaders.length >= 3 && columnCount >= 3,
          header_row_count: rows.filter(function(row) { return Boolean(row.querySelector("th")); }).length,
          data_row_count: dataRows.length,
          column_count: columnCount,
          column_headers: columnHeaders,
          merged_cell_count: mergedCells.length,
          rowspan_count: cells.filter(function(cell) { return Number(cell.getAttribute("rowspan")) > 1; }).length,
          colspan_count: cells.filter(function(cell) { return Number(cell.getAttribute("colspan")) > 1; }).length,
          status_icon_states: iconStates,
          has_declared_legend: extractLegend(doc).present
        };
      });
    }

    function formatBytes(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    async function sha256(text) {
      const encoded = new TextEncoder().encode(text);
      const buffer = await crypto.subtle.digest("SHA-256", encoded);
      return Array.from(new Uint8Array(buffer)).map(function(byte) {
        return byte.toString(16).padStart(2, "0");
      }).join("");
    }

    function setError(message) {
      errorBox.textContent = message;
      errorBox.hidden = !message;
    }

    function setFileInfo(file) {
      fileInfo.replaceChildren();
      const name = document.createElement("div");
      name.className = "file-name";
      name.textContent = file.name;
      const stats = document.createElement("div");
      stats.className = "file-stats";
      stats.textContent = formatBytes(file.size) + " · reading locally";
      fileInfo.appendChild(name);
      fileInfo.appendChild(stats);
    }

    function addMetadataItem(label, value, kind, wide) {
      const item = document.createElement("div");
      item.className = "metadata-item" + (wide ? " wide" : "");
      const labelNode = document.createElement("div");
      labelNode.className = "meta-label";
      labelNode.textContent = label;
      const valueNode = document.createElement("div");
      valueNode.className = "metadata-value" + (kind ? " " + kind : "");
      valueNode.textContent = Array.isArray(value) ? (value.length ? value.join(" · ") : "—") : String(value);
      item.appendChild(labelNode);
      item.appendChild(valueNode);
      metadataGrid.appendChild(item);
    }

    async function buildMetadata(file, source) {
      const doc = new DOMParser().parseFromString(source, "text/html");
      const title = clean(textOf(doc.querySelector("title"))) || clean(textOf(doc.querySelector("h1"))) || file.name.replace(/\.(html?|HTML?)$/, "");
      const descriptionNode = doc.querySelector('meta[name="description"]');
      const description = descriptionNode ? descriptionNode.getAttribute("content") : "";
      const firstParagraph = textOf(doc.querySelector("p"));
      const bodyText = textOf(doc.body);
      const purpose = limitWords(description || firstParagraph || bodyText, 30);
      const headings = Array.from(doc.querySelectorAll("h1, h2, h3")).map(textOf).filter(Boolean).slice(0, 12);
      const tables = doc.querySelectorAll("table");
      const visualCount = doc.querySelectorAll("img, svg, video, canvas, figure").length + (source.match(/<ac:(?:image|emoticon)\b/gi) || []).length;
      const tableMetadata = extractTableMetadata(doc);
      const legend = extractLegend(doc);
      const hash = await sha256(source);
      return {
        metadata_version: "riskon.page_card.v1",
        title: title,
        purpose: purpose || "No short purpose found in the page.",
        topics: extractTopics(doc, bodyText),
        acronyms: extractAcronyms(source),
        likely_scope_terms: extractScopeTerms(source),
        contains_table: tables.length > 0,
        contains_visual: visualCount > 0,
        source_filename: file.name,
        source_hash: "sha256:" + hash,
        table_count: tables.length,
        visual_count: visualCount,
        tables: tableMetadata,
        legend: legend,
        heading_count: headings.length,
        headings: headings,
        word_count: bodyText ? bodyText.split(/\s+/).filter(Boolean).length : 0
      };
    }

    function renderMetadata(metadata) {
      emptyResult.hidden = true;
      resultContent.hidden = false;
      resultTitle.textContent = metadata.title;
      hashRow.textContent = metadata.source_hash;
      metadataGrid.replaceChildren();
      addMetadataItem("Purpose", metadata.purpose);
      addMetadataItem("Topics", metadata.topics, "list");
      addMetadataItem("Acronyms", metadata.acronyms, "list");
      addMetadataItem("Likely scope", metadata.likely_scope_terms, "list");
      addMetadataItem("Table", metadata.contains_table ? "true" : "false", "boolean");
      addMetadataItem("Visual", metadata.contains_visual ? "true" : "false", "boolean");
      addMetadataItem("Structure", metadata.table_count + " table(s) · " + metadata.visual_count + " visual(s)");
      if (metadata.tables.length) {
        const table = metadata.tables[0];
        addMetadataItem(
          "Table map",
          (table.matrix ? "matrix" : "table") + " · " + table.data_row_count + " data row(s) · " + table.column_count + " column(s)",
        );
        addMetadataItem("Table columns", table.column_headers, "list", true);
        addMetadataItem("Merged cells", table.merged_cell_count + " · rowspan " + table.rowspan_count + " · colspan " + table.colspan_count);
        addMetadataItem("Declared legend", metadata.legend.present ? metadata.legend.entries.length + " icon meaning(s)" : "not found");
      }
      addMetadataItem("Words", metadata.word_count);
      currentJson = JSON.stringify(metadata, null, 2);
      jsonOutput.textContent = currentJson;
    }

    async function handleFile(file) {
      setError("");
      if (!file) return;
      if (file.size > MAX_BYTES) {
        setError("This demo accepts HTML files up to 8 MB.");
        return;
      }
      if (!/\.html?$/i.test(file.name) && file.type && file.type !== "text/html") {
        setError("Please choose an .html or .htm file.");
        return;
      }
      setFileInfo(file);
      try {
        const source = await file.text();
        if (!clean(source)) throw new Error("The selected file is empty.");
        renderMetadata(await buildMetadata(file, source));
      } catch (error) {
        setError(error.message || "Could not read this HTML file locally.");
      }
    }

    browseButton.addEventListener("click", function(event) {
      event.stopPropagation();
      fileInput.click();
    });
    fileInput.addEventListener("change", function() { handleFile(fileInput.files[0]); });
    dropzone.addEventListener("click", function() { fileInput.click(); });
    dropzone.addEventListener("keydown", function(event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });
    ["dragenter", "dragover"].forEach(function(eventName) {
      dropzone.addEventListener(eventName, function(event) {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach(function(eventName) {
      dropzone.addEventListener(eventName, function(event) {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
      });
    });
    dropzone.addEventListener("drop", function(event) {
      handleFile(event.dataTransfer.files[0]);
    });
    copyButton.addEventListener("click", async function() {
      if (!currentJson) return;
      try {
        await navigator.clipboard.writeText(currentJson);
        copyButton.textContent = "Copied";
        window.setTimeout(function() { copyButton.textContent = "Copy JSON"; }, 1400);
      } catch (error) {
        copyButton.textContent = "Copy unavailable";
      }
    });
  </script>
</body>
</html>
"""
