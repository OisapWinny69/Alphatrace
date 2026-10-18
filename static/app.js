const form = document.querySelector("#research-form");
const queryInput = document.querySelector("#company-query");
const formError = document.querySelector("#form-error");
const landing = document.querySelector("#landing");
const workspace = document.querySelector("#workspace");
const workspaceTitle = document.querySelector("#workspace-title");
const workspaceSubtitle = document.querySelector("#workspace-subtitle");
const progressPanel = document.querySelector("#progress-panel");
const progressLabel = document.querySelector("#progress-label");
const progressCount = document.querySelector("#progress-count");
const progressFill = document.querySelector("#progress-fill");
const stageList = document.querySelector("#stage-list");
const reportPanel = document.querySelector("#report");
const newResearch = document.querySelector("#new-research");
let researchMode = "offline";

fetch("/api/health")
  .then((response) => response.json())
  .then((payload) => {
    if (payload.mode === "live") researchMode = "live";
  })
  .catch(() => {});

const stages = [
  "Resolve company identity",
  "Select business model and peers",
  "Build source plan",
  "Retrieve public documents",
  "Parse documents and verify quotes",
  "Calculate derived metrics",
  "Detect divergences",
  "Generate competing hypotheses",
  "Search for contradictory evidence",
  "Run falsification tests",
  "Rank surviving discoveries",
  "Prepare auditable report",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, suffix = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${number.toFixed(2)}${suffix}`;
}

function renderStages(activeIndex, complete = false) {
  stageList.innerHTML = stages.map((stage, index) => {
    const className = complete || index < activeIndex ? "done" : index === activeIndex ? "active" : "";
    return `<div class="stage-item ${className}">${escapeHtml(stage)}</div>`;
  }).join("");
  const shownIndex = Math.min(activeIndex + 1, stages.length);
  progressLabel.textContent = complete ? "Research complete — discovery assembled" : stages[activeIndex];
  progressCount.textContent = `${String(shownIndex).padStart(2, "0")} / ${stages.length}`;
  progressFill.style.width = `${complete ? 100 : Math.max(6, (activeIndex / (stages.length - 1)) * 100)}%`;
}

function lineChart(metrics) {
  const periods = metrics.periods || [];
  const series = [
    { label: "Reported GNPA", values: metrics.reported_gnpa || [], color: "#c9f36b" },
    { label: "Write-off adjusted", values: metrics.writeoff_adjusted_gnpa || [], color: "#73e6dc" },
    { label: "Peer average", values: metrics.peer_average_gnpa || [], color: "#ffb86b" },
  ];
  const width = 760;
  const height = 220;
  const pad = { top: 18, right: 18, bottom: 38, left: 42 };
  const allValues = series.flatMap((item) => item.values.map(Number));
  const min = Math.min(...allValues) - 0.08;
  const max = Math.max(...allValues) + 0.08;
  const x = (index) => pad.left + (index * (width - pad.left - pad.right)) / Math.max(periods.length - 1, 1);
  const y = (value) => pad.top + ((max - value) * (height - pad.top - pad.bottom)) / Math.max(max - min, 0.01);
  const grid = [0, 1, 2, 3].map((tick) => {
    const value = min + ((max - min) * tick) / 3;
    const yy = y(value);
    return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}" stroke="rgba(189,222,242,.12)"/><text x="8" y="${yy + 3}" fill="#71899a" font-size="10">${value.toFixed(1)}%</text>`;
  }).join("");
  const paths = series.map((item) => {
    const points = item.values.map((value, index) => `${x(index)},${y(Number(value))}`).join(" ");
    const dots = item.values.map((value, index) => `<circle cx="${x(index)}" cy="${y(Number(value))}" r="3" fill="${item.color}"/>`).join("");
    return `<polyline points="${points}" fill="none" stroke="${item.color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${dots}`;
  }).join("");
  const labels = periods.map((period, index) => `<text x="${x(index)}" y="${height - 12}" text-anchor="middle" fill="#71899a" font-size="9">${escapeHtml(period)}</text>`).join("");
  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Asset quality trend chart">${grid}${paths}${labels}</svg>`;
}

function renderEvidence(evidence) {
  return evidence.map((item) => `
    <a class="evidence-item" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
      <span class="evidence-tier">T${escapeHtml(item.source_tier)}</span>
      <span class="evidence-body"><strong>${escapeHtml(item.claim)}</strong><small>${escapeHtml(item.publisher)} · ${escapeHtml(item.period)} · p. ${escapeHtml(item.page)}</small><p>“${escapeHtml(item.quote)}”</p></span>
      <span class="evidence-role ${item.role === "opposing" ? "opposing" : ""}">${item.role === "opposing" ? "Opposing" : "Supports"} ↗</span>
    </a>`).join("");
}

function renderClaims(claims, evidence) {
  const evidenceById = Object.fromEntries(evidence.map((item) => [item.id, item]));
  return claims.map((claim) => {
    const linkedEvidence = claim.evidence_ids.map((id) => {
      const item = evidenceById[id];
      if (!item) return `<span class="claim-ref">${escapeHtml(id)}</span>`;
      return `<a class="claim-ref" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(id)} ↗</a>`;
    }).join(" ");
    const confidence = Number(claim.confidence);
    return `<div class="claim-item"><div class="claim-meta"><span class="claim-type">${escapeHtml(claim.claim_type.replaceAll("_", " "))}</span><span>${Number.isFinite(confidence) ? `${Math.round(confidence * 100)}% confidence` : "confidence unavailable"}</span><span>${escapeHtml(claim.independent_source_families)} independent families</span></div><strong>${escapeHtml(claim.text)}</strong><div class="claim-links">Evidence: ${linkedEvidence || "none"}${claim.calculation_ids.length ? `<span> · Calculations: ${escapeHtml(claim.calculation_ids.join(", "))}</span>` : ""}</div></div>`;
  }).join("");
}

function renderConflicts(conflicts) {
  return conflicts.map((conflict) => `<div class="conflict-item"><div class="conflict-head"><span class="conflict-severity ${escapeHtml(conflict.severity)}">${escapeHtml(conflict.severity)}</span><strong>${escapeHtml(conflict.conflict_type)}</strong><span class="conflict-status">${escapeHtml(conflict.resolution_status)}</span></div><div class="conflict-grid"><div><small>Source A / claim</small><p>${escapeHtml(conflict.claim_a)}</p></div><div><small>Source B / claim</small><p>${escapeHtml(conflict.claim_b)}</p></div></div><p class="conflict-explanation"><b>Possible explanation:</b> ${escapeHtml(conflict.possible_explanation)}</p></div>`).join("");
}

function renderResearchTrail(events) {
  return events.map((event) => `<details class="trail-item"><summary><span class="trail-sequence">${String(event.sequence).padStart(2, "0")}</span><span><b>${escapeHtml(event.action.replaceAll("_", " "))}</b><small>${escapeHtml(event.stage)} · ${escapeHtml(event.status)}</small></span></summary><p>${escapeHtml(event.summary)}</p><div class="trail-links">${event.source_ids?.length ? `Sources: ${escapeHtml(event.source_ids.join(", "))}` : ""}${event.evidence_ids?.length ? ` · Evidence: ${escapeHtml(event.evidence_ids.join(", "))}` : ""}${event.calculation_ids?.length ? ` · Calculations: ${escapeHtml(event.calculation_ids.join(", "))}` : ""}${event.conflict_ids?.length ? ` · Conflicts: ${escapeHtml(event.conflict_ids.join(", "))}` : ""}</div></details>`).join("");
}

function renderReport(report) {
  const company = report.company;
  const metrics = report.metrics;
  const passedTests = report.falsification_tests.filter((test) => test.status === "PASS").length;
  const calculationTiles = [
    ["Headline GNPA", `${formatNumber(metrics.reported_gnpa[0])}% → ${formatNumber(metrics.reported_gnpa.at(-1))}%`, "reported"],
    ["Adjusted improvement", `${formatNumber(metrics.adjusted_improvement)} pp`, "write-off adjusted"],
    ["Write-off rate growth", `${formatNumber(metrics.write_off_rate[0])}% → ${formatNumber(metrics.write_off_rate.at(-1))}%`, "observation window"],
    ["Loan-book growth", `${formatNumber(metrics.loan_book[0])} → ${formatNumber(metrics.loan_book.at(-1))}`, `${formatNumber(metrics.loan_book.at(-1) / metrics.loan_book[0] * 100 - 100)}% total`],
  ];
  reportPanel.innerHTML = `
    <div class="report-notice">${escapeHtml(report.notice)}</div>
    <div class="report-grid">
      <article class="report-card discovery-card full"><div class="report-label">The discovery · ${escapeHtml(company.symbol)} · ${escapeHtml(company.business_model)}</div><span class="strength-chip"><i></i>${escapeHtml(report.evidence_strength)} evidence</span><h3>${escapeHtml(report.discovery)}</h3></article>
      <article class="report-card"><div class="report-label">Why it matters</div><ul class="why-list">${report.why_it_matters.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article>
      <article class="report-card score-panel"><div><div class="report-label">Evidence strength</div><div class="big-score">${escapeHtml(report.evidence_strength)} <span>signal</span></div></div><p class="score-copy">${escapeHtml(report.strength_reasoning)}</p><div class="score-copy">${passedTests} / ${report.falsification_tests.length} falsification tests survived.</div></article>
      <article class="report-card full"><div class="report-label">Key numbers</div><div class="metric-grid">${calculationTiles.map(([title, value, note]) => `<div class="metric-tile"><small>${escapeHtml(title)}</small><strong>${escapeHtml(value)}</strong><em>${escapeHtml(note)}</em></div>`).join("")}</div></article>
      <article class="report-card full"><div class="report-label">The divergence over time</div><div class="chart-wrap">${lineChart(metrics)}</div><div class="chart-legend"><span>Reported GNPA</span><span>Write-off adjusted</span><span>Peer average</span></div></article>
      <article class="report-card full"><div class="report-label">Timeline</div><div class="timeline">${report.timeline.map((event) => `<div class="timeline-item ${event.tone === "challenge" ? "challenge" : ""}"><small>${escapeHtml(event.period)}</small><strong>${escapeHtml(event.label)}</strong><p>${escapeHtml(event.detail)}</p></div>`).join("")}</div></article>
       <article class="report-card full"><div class="report-label">Evidence ledger · click any claim to open its source</div><div class="evidence-list">${renderEvidence(report.evidence)}</div></article>
       <article class="report-card full"><div class="report-label">Claims ledger · every major conclusion has linked evidence</div><div class="claims-list">${renderClaims(report.claims || [], report.evidence)}</div></article>
       <article class="report-card full"><div class="report-label">Conflicts · what disagrees with the leading story</div><div class="conflicts-list">${renderConflicts(report.conflicts || [])}</div></article>
       <div class="two-col full"><article class="report-card"><div class="report-label">Counterargument</div><div class="quote-block">${escapeHtml(report.counterargument)}</div></article><article class="report-card"><div class="report-label">Falsification condition</div><div class="falsify-box">${escapeHtml(report.falsification_condition)}</div></article></div>
      <article class="report-card full"><div class="report-label">Falsification tests</div><div class="test-list">${report.falsification_tests.map((test) => `<div class="test-item"><span class="test-status ${test.status.toLowerCase()}">${escapeHtml(test.status)}</span><span class="test-body"><strong>${escapeHtml(test.name)}</strong><p>${escapeHtml(test.explanation)}</p></span></div>`).join("")}</div></article>
      <article class="report-card full"><div class="report-label">Hypothesis board</div><div class="hypothesis-list">${report.hypotheses.map((hypothesis, index) => `<div class="hypothesis-item"><span class="hypothesis-rank">0${index + 1}</span><span class="hypothesis-body"><strong>${escapeHtml(hypothesis.statement)}</strong><small>${escapeHtml(hypothesis.lens)} · score ${escapeHtml(hypothesis.score)}</small></span><span class="hypothesis-state ${hypothesis.status}">${escapeHtml(hypothesis.status)}</span></div>`).join("")}</div></article>
       <article class="report-card full"><div class="report-label">Reproducible calculations</div><div class="evidence-list">${report.numbers.map((number) => `<div class="evidence-item"><span class="evidence-tier">fx</span><span class="evidence-body"><strong>${escapeHtml(number.name)} · ${formatNumber(number.result)} ${escapeHtml(number.unit)}</strong><small>${escapeHtml(number.formula)}</small><p>${escapeHtml(number.interpretation)}</p></span></div>`).join("")}</div></article>
       <article class="report-card full"><div class="report-label">Research trail · replayable decision log</div><div class="trail-list">${renderResearchTrail(report.events || [])}</div></article>
     </div>`;
}

async function runInvestigation(query) {
  formError.textContent = "";
  landing.classList.add("hidden");
  workspace.classList.remove("hidden");
  progressPanel.classList.remove("hidden");
  reportPanel.classList.add("hidden");
  workspaceTitle.textContent = "Preparing your investigation";
  workspaceSubtitle.textContent = "Building an evidence graph from public sources.";
  renderStages(0);
  workspace.scrollIntoView({ behavior: "smooth", block: "start" });

  let currentStage = 0;
  const timer = window.setInterval(() => {
    currentStage = Math.min(currentStage + 1, stages.length - 1);
    renderStages(currentStage);
  }, 250);

  try {
     const response = await fetch("/api/research", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, mode: researchMode }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The research run could not start.");
    window.clearInterval(timer);
    renderStages(stages.length - 1, true);
    const report = payload.report;
    workspaceTitle.textContent = `${report.company.name} · research complete`;
    workspaceSubtitle.textContent = `${report.company.symbol} · ${report.company.business_model} · ${report.evidence.length} evidence records connected`;
    renderReport(report);
    reportPanel.classList.remove("hidden");
    progressPanel.classList.add("hidden");
    reportPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    window.clearInterval(timer);
    progressPanel.classList.add("hidden");
    workspaceTitle.textContent = "Investigation could not start";
    workspaceSubtitle.textContent = "Check the company symbol and try again.";
    formError.textContent = error.message;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (query) runInvestigation(query);
});

document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.example;
    runInvestigation(button.dataset.example);
  });
});

newResearch.addEventListener("click", () => {
  workspace.classList.add("hidden");
  landing.classList.remove("hidden");
  reportPanel.innerHTML = "";
  queryInput.focus();
  window.scrollTo({ top: 0, behavior: "smooth" });
});
