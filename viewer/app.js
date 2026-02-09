let DATA = null;
let currentView = "list";
let network = null;

async function init() {
  const resp = await fetch("data.json");
  DATA = await resp.json();
  renderStats();
  renderFilters();
  renderList();

  document.getElementById("search").addEventListener("input", renderList);
  document.getElementById("filter-type").addEventListener("change", renderList);
  document.getElementById("filter-tag").addEventListener("change", renderList);

  window.addEventListener("popstate", handleHash);
  handleHash();
}

function handleHash() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash && DATA.entries.some((e) => e.path === hash)) {
    showDetail(hash);
  } else if (!hash) {
    showView("list");
  }
}

function renderStats() {
  const s = DATA.stats;
  document.getElementById("stats").textContent =
    `${s.total} entries · ${s.total_edges} edges · ${s.tags.length} tags`;
}

function renderFilters() {
  const typeSelect = document.getElementById("filter-type");
  const tagSelect = document.getElementById("filter-tag");

  Object.entries(DATA.stats.by_type)
    .sort((a, b) => b[1] - a[1])
    .forEach(([type, count]) => {
      const opt = document.createElement("option");
      opt.value = type;
      opt.textContent = `${type} (${count})`;
      typeSelect.appendChild(opt);
    });

  DATA.stats.tags.forEach((tag) => {
    const opt = document.createElement("option");
    opt.value = tag;
    opt.textContent = tag;
    tagSelect.appendChild(opt);
  });
}

function showView(view) {
  currentView = view;
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.getElementById(`view-${view}`).classList.add("active");
  document.querySelectorAll("nav button").forEach((btn) => btn.classList.remove("active"));
  document.querySelector(`nav button[data-view="${view}"]`).classList.add("active");

  if (view === "graph" && !network) {
    renderGraph();
  }
}

function getFiltered() {
  const q = document.getElementById("search").value.toLowerCase();
  const type = document.getElementById("filter-type").value;
  const tag = document.getElementById("filter-tag").value;

  return DATA.entries.filter((e) => {
    if (type && e.type !== type) return false;
    if (tag && !e.tags.includes(tag)) return false;
    if (q) {
      const text = `${e.title} ${e.summary} ${e.tags.join(" ")}`.toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });
}

function renderList() {
  const entries = getFiltered();
  const container = document.getElementById("entry-list");
  container.innerHTML = entries
    .map(
      (e) => `
    <div class="entry-card" onclick="showDetail('${e.path}')">
      <h3><span class="type-badge type-${e.type}">${e.type}</span> ${esc(e.title)}</h3>
      <div class="meta">
        ${e.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join(" ")}
        · ${e.edges.length} edges · ${e.backlinks.length} backlinks
        · ${e.created}
      </div>
      <div class="summary">${esc(e.summary)}</div>
    </div>
  `
    )
    .join("");
}

function showDetail(path) {
  const entry = DATA.entries.find((e) => e.path === path);
  if (!entry) return;

  if (location.hash !== "#" + encodeURIComponent(path)) {
    history.pushState(null, "", "#" + encodeURIComponent(path));
  }

  showView("detail");
  const panel = document.getElementById("detail-content");

  const edgesHtml = entry.edges.length
    ? entry.edges
        .map(
          (e) => `
      <div class="connection-item">
        <span class="connection-label">${esc(e.label)}</span>
        <a href="#" onclick="showDetail('${e.path}'); return false;">${pathTitle(e.path)}</a>
        ${e.description ? `<span style="color:var(--text-muted)">— ${esc(e.description)}</span>` : ""}
      </div>`
        )
        .join("")
    : "<div style='color:var(--text-muted)'>None</div>";

  const backlinksHtml = entry.backlinks.length
    ? entry.backlinks
        .map(
          (b) => `
      <div class="connection-item">
        <span class="connection-label">${esc(b.label)}</span>
        <a href="#" onclick="showDetail('${b.path}'); return false;">${esc(b.title)}</a>
        ${b.description ? `<span style="color:var(--text-muted)">— ${esc(b.description)}</span>` : ""}
      </div>`
        )
        .join("")
    : "<div style='color:var(--text-muted)'>None</div>";

  const sourcesHtml = entry.sources.length
    ? entry.sources
        .map((s) => `<div><a href="${esc(s.url)}" target="_blank">${esc(s.title || s.url)}</a></div>`)
        .join("")
    : "";

  panel.innerHTML = `
    <button class="back-btn" onclick="history.pushState(null, '', location.pathname); showView('list'); renderList();">← Back to list</button>
    <h2>${esc(entry.title)}</h2>
    <div class="detail-meta">
      <span class="type-badge type-${entry.type}">${entry.type}</span>
      ${entry.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join(" ")}
      <span>${entry.created}</span>
    </div>
    <div style="color:var(--text-muted);margin-bottom:16px;font-size:15px;">${esc(entry.summary)}</div>
    <div class="detail-body">${entry.body_html || "<em>No rendered content</em>"}</div>
    ${sourcesHtml ? `<div class="connections"><h3>Sources</h3>${sourcesHtml}</div>` : ""}
    <div class="connections">
      <h3>Edges (${entry.edges.length})</h3>
      ${edgesHtml}
    </div>
    <div class="connections">
      <h3>Backlinks (${entry.backlinks.length})</h3>
      ${backlinksHtml}
    </div>
  `;

  panel.querySelector(".detail-body").addEventListener("click", (e) => {
    const a = e.target.closest("a");
    if (!a) return;
    const href = a.getAttribute("href");
    if (href && href.startsWith("/knowledge/") && href.endsWith(".md")) {
      e.preventDefault();
      showDetail(href);
    }
  });

  if (typeof renderMathInElement === "function") {
    renderMathInElement(panel.querySelector(".detail-body"), {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
    });
  }
}

const TYPE_COLORS = {
  concept: "#58a6ff",
  reference: "#bc8cff",
  insight: "#d29922",
  question: "#f85149",
  note: "#3fb950",
};

function renderGraph() {
  const container = document.getElementById("graph-container");

  const entryPaths = new Set(DATA.entries.map((e) => e.path));

  const nodes = new vis.DataSet(
    DATA.graph.nodes
      .filter((n) => entryPaths.has(n.id))
      .map((n) => ({
        id: n.id,
        label: n.title,
        color: {
          background: TYPE_COLORS[n.type] || "#8b949e",
          border: TYPE_COLORS[n.type] || "#8b949e",
          highlight: { background: "#fff", border: TYPE_COLORS[n.type] || "#8b949e" },
        },
        font: { color: "#e6edf3", size: 13 },
        shape: "dot",
        size: 12 + (DATA.entries.find((e) => e.path === n.id)?.backlinks.length || 0) * 4,
      }))
  );

  const edges = new vis.DataSet(
    DATA.graph.edges
      .filter((e) => entryPaths.has(e.from) && entryPaths.has(e.to))
      .map((e, i) => ({
        id: i,
        from: e.from,
        to: e.to,
        label: e.label,
        font: { color: "#8b949e", size: 10, strokeWidth: 0 },
        color: { color: "#30363d", highlight: "#58a6ff" },
        arrows: "to",
      }))
  );

  network = new vis.Network(container, { nodes, edges }, {
    physics: {
      forceAtlas2Based: {
        gravitationalConstant: -40,
        centralGravity: 0.005,
        springLength: 150,
        springConstant: 0.08,
      },
      solver: "forceAtlas2Based",
      stabilization: { iterations: 100 },
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
    },
    layout: { improvedLayout: true },
  });

  network.on("click", (params) => {
    if (params.nodes.length > 0) {
      showDetail(params.nodes[0]);
    }
  });
}

function pathTitle(path) {
  const entry = DATA.entries.find((e) => e.path === path);
  return entry ? esc(entry.title) : path.split("/").pop().replace(".md", "");
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

document.addEventListener("DOMContentLoaded", init);
