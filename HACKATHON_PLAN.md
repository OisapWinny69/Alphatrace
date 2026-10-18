# AlphaTrace Hackathon Plan

## 1. Winning thesis

AlphaTrace is an autonomous public-source financial research investigator. It does not try to predict prices, recommend trades, or summarize a news feed. It finds a non-obvious relationship across time, peers, and independent source types; calculates the relationship deterministically; actively searches for reasons it could be wrong; and presents a report that a judge can audit from claim to quote to calculation.

The central product promise is:

> **One defensible discovery, with the evidence and the failure conditions visible.**

## 2. Judging rubric mapped to product behavior

| Judging criterion | AlphaTrace proof |
| --- | --- |
| Discovery quality | Computed divergences and competing hypotheses, not a summary of one document |
| Evidence quality | A claim ledger where every major claim links to a verified quote, URL, period, and page/location |
| Novelty | Stock-versus-flow, narrative-versus-number, peer-relative, and disclosure-drift calculations that ordinary dashboards do not print |
| Temporal reasoning | Period-indexed facts, timelines, persistence checks, base-effect tests, and event ordering |
| Cross-source reasoning | Source tiers and publisher families; company filing checked against regulator, peer, rating, counterparty, or credible media evidence |
| Falsifiability | Five red-team tests, opposing evidence, counterargument, and a concrete future condition that would change the conclusion |
| Explainability | Replayable event trail linking source discovery, extraction, calculation, hypothesis, conflict, and final report |
| Robustness | Partial-source handling, quote verification, contradiction detection, and an explicit “no strong discovery” outcome |
| Generality & autonomy | Business-model metric packs and resolver-driven peer selection; no company-specific result templates |

## 3. Scope and non-goals

### In scope

- NIFTY 50 Banking, NBFC, and Financial Services companies in Track A.
- Other listed banks and NBFCs when a public source can resolve their identity and peer group.
- Public filings, annual reports, investor presentations, exchange announcements, RBI/IRDAI/SEBI material, rating rationales, peer disclosures, and credible financial media.
- A live source pipeline with a deterministic offline fixture fallback.
- A report with the eight required sections: Discovery, Why It Matters, Evidence, Timeline, Numbers, Counterargument, Falsification Condition, and Evidence Strength.

### Explicit non-goals

- Stock-price prediction.
- Buy/sell or portfolio recommendations.
- A general-purpose finance chatbot.
- A generic news summarizer.
- A visually elaborate trading terminal.
- Proprietary or paid data.
- A large multi-agent system whose coordination is harder to audit than the result.

## 4. First research pack

The first live pack targets banks and NBFCs because it gives the strongest generalizable discovery surface:

> **Is reported asset-quality improvement supported by the underlying flow of stress?**

The pack combines:

- GNPA and NNPA.
- Slippages, recoveries, and write-offs.
- Credit cost and provision coverage.
- Loan book/AUM growth.
- Restructured or stressed-book disclosures where available.
- Peer-relative changes and persistence across quarters.

The engine must not assume that every company reports every metric. Missing coverage lowers evidence strength and can produce “No strong discovery found.” It must never fill gaps with invented values.

Later packs can add bank funding mix/NIM, NBFC liability mix, and insurer growth/persistency/solvency metrics behind the same contracts.

## 5. System architecture

```text
Browser dashboard
        |
        v
HTTP API + run coordinator
        |
        +--> resolver and metric-pack selector
        +--> source discovery adapters
        +--> document fetch/cache/parser
        +--> fact and quote verifier
        +--> deterministic calculation engine
        +--> divergence detector
        +--> hypothesis and red-team coordinator
        +--> report validator/composer
        |
        v
SQLite run store + document cache + replay events
```

The system has one orchestrated pipeline, not twenty autonomous agents. Model calls are optional and replaceable. Deterministic code owns arithmetic, source identity, quote verification, independence metadata, conflict classification, evidence scoring, and final schema validation.

## 6. Source and provider policy

### Source hierarchy

1. NSE/BSE filings, quarterly results, annual reports, Basel disclosures, and official announcements.
2. Company investor presentations and earnings-call material.
3. RBI, IRDAI, SEBI, and other independent official publications.
4. CRISIL, ICRA, CARE, and India Ratings rationales.
5. Peer, parent, counterparty, and co-lending disclosures.
6. Credible financial media for context.

The source ledger records both document count and independent publisher-family count. Three documents from one company are not three independent confirmations.

### Search and AI adapters

- Tavily is the default search adapter when `TAVILY_API_KEY` is configured; Serper can be used as a compatible fallback.
- OpenAI is the initial structured reasoning adapter; the provider interface leaves room for Gemini and other OpenAI-compatible services.
- Offline mode remains a first-class mode and uses the same report contracts as live mode.
- Search results are candidate URLs only. A source becomes evidence only after retrieval, parsing, and quote verification.
- Secrets remain server-side and are read from environment variables only.

## 7. Evidence and reasoning contracts

Every extracted fact records:

- Company, metric, value, unit, period, segment, and reporting scope.
- Source document, canonical URL, publisher family, source tier, and publication date.
- Page or text location and the exact quote used.
- Quote verification status.

Every major claim records:

- Claim text and type.
- Evidence IDs and calculation IDs.
- Independent source-family count.
- Confidence and validation status.

Every calculation records:

- Formula, result, unit, input fact IDs, and interpretation.

Every final report must pass validation that:

- No major claim is unsupported.
- No displayed URL was invented by the model.
- No displayed quote failed verification.
- No report number bypassed deterministic calculations.
- Contradictory evidence is not suppressed.

## 8. Conflict and red-team design

Conflicts are first-class report objects, not hidden notes. Each conflict explains what disagrees, which sources disagree, the relevant period/metric, severity, and whether the conflict was resolved.

The leading hypothesis is challenged by:

1. Sector test — is the same divergence present in most peers?
2. Accounting-artifact test — could scope, merger, write-off, or definition drift explain it?
3. Base-effect test — does it survive two-year and three-year comparisons?
4. Macro/regulatory test — could an industry event explain the timing?
5. Disclosure-change test — did the company change what it reports?

Each result is `PASS`, `FAIL`, or `INCONCLUSIVE`, with evidence IDs and a human-readable explanation. A hypothesis that fails materially is downgraded or rejected.

## 9. Replayable evidence trail

The run store emits ordered events such as:

```text
resolve_company
select_metric_pack
select_peers
discover_sources
retrieve_document
parse_document
extract_fact
verify_quote
calculate_metric
detect_divergence
generate_hypothesis
find_opposing_evidence
classify_conflict
run_falsification_test
rank_hypothesis
compose_report
```

The UI exposes a compact event timeline with links to the relevant source, fact, calculation, or hypothesis. Replay replays persisted evidence and decisions; it does not silently rerun an unpredictable model call.

## 10. Delivery sequence

### Step 1 — Contracts and reproducibility

- Keep Python 3.12.8 pinned.
- Keep a committed lockfile.
- Add `make test` as the one canonical offline test command.
- Document setup, run, test, Docker, live configuration, and demo fallback.

### Step 2 — Auditability foundation

- Add claims, conflicts, provenance, quote status, and research events to the domain model.
- Add schema validation and tests for unsupported claims and failed quotes.

### Step 3 — Persistence and replay

- Persist runs, documents, facts, calculations, claims, hypotheses, conflicts, tests, evidence links, and events in SQLite.
- Add readback endpoints and reload a completed run after navigation.

### Step 4 — Public-source pipeline

- Add source discovery interface, safe HTTP fetcher, local cache, HTML parsing, page-preserving PDF boundary, and exact quote verification.
- Return partial coverage explicitly when a source fails.

### Step 5 — General live research pack

- Implement configurable bank/NBFC metric extraction and peer comparison.
- Never map a company to a prewritten result; facts and sources drive the outcome.

### Step 6 — Challenge and dashboard

- Add conflict table, red-team evidence, replay UI, source coverage, rejected hypotheses, JSON export, and print view.

### Step 7 — Demo hardening

- Run an unseen-company cold test.
- Build and run Docker.
- Keep a cached successful public-source run for outage recovery.
- Verify every demo claim has a clickable URL and quote.

## 11. Acceptance gates

The project is finals-ready when:

- The same pipeline runs for every supported Track A company without company-specific analysis code.
- A live or cached public-source run produces a non-obvious calculated relationship.
- At least two independent source families support each major discovery where coverage permits.
- Every major claim has a verified quote and URL.
- At least one competing hypothesis is rejected or downgraded.
- Conflicts, counterargument, falsification condition, and evidence strength are visible.
- The five red-team tests are visible with evidence.
- A judge can replay the evidence trail from discovery to report.
- Weak or incomplete evidence is disclosed rather than padded.
- `make test` passes offline and Docker builds from a clean environment.

## 12. Demo script

1. Enter a company by symbol.
2. Show the resolver selecting business model, metric pack, and peers.
3. Let the progress view reveal source discovery and calculations.
4. Open the final Discovery and Why It Matters.
5. Click through two independent source types and read the exact quotes.
6. Expand Numbers to show formulas and input facts.
7. Open Conflicts and the rejected hypothesis.
8. Run through the five red-team tests.
9. Show the Counterargument and Falsification Condition.
10. Replay the event trail and finish on the evidence-strength explanation.

## 13. Risk register and fallback behavior

| Risk | Fallback |
| --- | --- |
| Exchange blocks or rate-limits a request | Use cached document, company IR copy, or mark partial coverage |
| Search API unavailable | Direct official-source adapters plus cached corpus |
| AI provider unavailable | Deterministic calculations and template-free structured offline mode |
| PDF extraction is incomplete | Keep page/text failure visible and exclude unverifiable claims |
| Insufficient independent evidence | Downgrade strength or return no strong discovery |
| Live run too slow for judging | Pre-cache a successful public-source run and show provenance honestly |
| Conflicting definitions | Surface conflict and avoid combining incompatible periods |
