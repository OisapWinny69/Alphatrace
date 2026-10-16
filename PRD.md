# SignalLens Product Requirements Document

## 1. Product overview

### Product name

**SignalLens**

### Product type

No-login web application for autonomous financial research.

### Chosen hackathon track

**Track A — Banking, NBFCs & Financial Services**

### One-line description

> SignalLens investigates public financial information, detects non-obvious divergences across time and peers, challenges its own conclusions, and produces one auditable financial discovery.

### Core product principle

SignalLens must not behave like a finance chatbot, news summarizer, generic report generator, single-document question-answering tool, stock-price prediction system, or investment recommendation engine. It must behave like an autonomous research investigator:

```text
Company
→ Research plan
→ Public evidence
→ Structured facts
→ Deterministic calculations
→ Divergence detection
→ Hypotheses
→ Counter-evidence
→ Falsification
→ Auditable discovery
```

## 2. Problem statement

Financial information about Indian listed companies is distributed across quarterly results, annual reports, NSE/BSE filings, investor presentations, earnings-call transcripts, RBI publications, rating-agency rationales, peer-company disclosures, counterparty disclosures, and credible financial news.

Conventional financial tools usually summarize these documents independently. They often fail to connect facts across documents, compare multiple periods, compare companies against peers, detect narrative-versus-number mismatches, identify changing definitions, test whether a finding is company-specific or sector-wide, or show what evidence would disprove a conclusion.

SignalLens addresses this by computing relationships first and asking an AI model to interpret and explain detected patterns second.

## 3. Goals

### Primary goals

1. Accept any supported NIFTY 50 Track A company by name or symbol.
2. Resolve the company and classify its business model.
3. Identify relevant peers automatically.
4. Gather public financial evidence.
5. Extract source-linked facts.
6. Calculate derived financial metrics deterministically.
7. Detect unusual divergences and temporal changes.
8. Generate multiple competing hypotheses.
9. Search for supporting and contradictory evidence.
10. Run explicit falsification tests.
11. Produce one complete, auditable discovery dashboard.
12. Work without login or signup.
13. Support an offline fixture mode for development and demo reliability.
14. Avoid hard-coded conclusions for individual companies.

### Secondary goals

- Persist research runs for replay.
- Cache downloaded public documents.
- Provide a printable report view.
- Support live research on an unseen company.
- Show rejected hypotheses and failed tests honestly.
- Make every major claim traceable to a source.

### Non-goals

SignalLens will not provide buy/sell recommendations, predict stock prices, manage portfolios, execute trades, require user accounts in the first release, use paid or proprietary financial datasets, pretend that five company-authored documents are five independent sources, allow the LLM to invent URLs or perform unchecked arithmetic, or hide uncertainty and failed falsification tests.

## 4. Target users

### Primary user

Hackathon judges evaluating whether the system can autonomously investigate a judge-selected company.

### Secondary users

- Financial researchers
- Equity analysts
- Students
- Investors seeking auditable public-source research
- Demonstrators evaluating autonomous research workflows

### User success criterion

A user should be able to enter a company and understand what the system discovered, why the discovery is unusual, which numbers support it, which sources support it, what evidence contradicts it, what alternative explanation exists, and what future evidence would change the conclusion.

## 5. Product experience

### 5.1 Landing page

The landing page requires no login.

Required sections:

- SignalLens brand and positioning statement
- Track A badge: Banking · NBFCs · Financial Services
- Company search input
- Start investigation action
- Example companies
- Short explanation of the investigation method
- Visual pipeline: Resolve → Collect → Calculate → Detect → Challenge → Prove
- Trust indicators: public sources, source-linked claims, deterministic calculations, counterargument, no recommendations

Example inputs include HDFCBANK, ICICIBANK, BAJFINANCE, SHRIRAMFIN, and SBILIFE. These are examples only and must not produce hard-coded findings.

### 5.2 Investigation setup

After a company is entered, the application displays:

- Resolved company name
- NSE/BSE symbol
- Business model
- Sector
- Official source links
- Automatically selected peers
- Applicable metric pack
- Selected investigation lenses
- Estimated source count
- Start action

Supported business models:

```text
Bank
NBFC
Insurer
Financial holding company
```

If a company cannot be resolved, the UI must explain the issue and suggest an NSE-symbol format. If source coverage is insufficient, the system must say so and downgrade the result instead of inventing a conclusion.

### 5.3 Research progress

The user sees live stage progress:

1. Resolve company identity
2. Select business model and metric pack
3. Select peers
4. Build source plan
5. Retrieve public documents
6. Parse documents
7. Extract facts
8. Verify exact quotes
9. Calculate derived metrics
10. Detect divergences
11. Generate hypotheses
12. Gather supporting evidence
13. Search for contradictions
14. Run falsification tests
15. Rank hypotheses
16. Build final report

Each stage may show source counts, documents downloaded, pages parsed, facts extracted, calculations completed, contradictions detected, rejected hypotheses, warnings, and retry/fallback status. A generic indefinite spinner is not sufficient.

### 5.4 Results dashboard

The result page must contain all eight hackathon output elements:

1. The Discovery
2. Why It Matters
3. Evidence
4. Timeline
5. Numbers
6. Counterargument
7. Falsification Condition
8. Evidence Strength

Additional sections should include a key-metrics chart, peer comparison chart, divergence score, contradiction panel, falsification test results, rejected hypotheses, calculation trace, research log, source ledger, downloadable JSON, and a print-friendly report view.

## 6. Research methodology

### 6.1 Source hierarchy

#### Tier 1 — Primary filings

- NSE filings
- BSE filings
- Quarterly results
- Annual reports
- Basel III disclosures
- Exchange announcements

#### Tier 2 — Company narrative

- Investor presentations
- Earnings-call transcripts
- Management commentary

#### Tier 3 — Independent official sources

- RBI circulars
- RBI Financial Stability Reports
- RBI Trend and Progress reports
- RBI sectoral credit data
- IRDAI data
- SEBI publications

#### Tier 4 — Rating agencies

- CRISIL
- ICRA
- CARE
- India Ratings

#### Tier 5 — Peer and counterparty filings

- Peer companies
- Financing partners
- Co-lending partners
- Parent companies
- Funding counterparties

#### Tier 6 — Credible financial media

- Mint
- Economic Times
- Business Standard
- Moneycontrol
- BloombergQuint or equivalent credible sources

News should generally provide context rather than serve as the sole support for a major numerical claim.

### 6.2 Source independence

The system distinguishes the number of documents, document types, publisher families, and independent evidence tiers. An annual report, investor presentation, and earnings-call transcript from the same company are not three independent sources.

A finding should preferably include evidence from multiple publisher families, such as a company filing, a peer disclosure, and RBI or rating-agency evidence.

### 6.3 Fact extraction

Every fact must include:

```typescript
type Fact = {
  id: string;
  company: string;
  metric: string;
  value: number | string;
  unit?: string;
  period: string;
  segment?: string;
  scope?: "standalone" | "consolidated" | "unknown";
  sourceDocumentId: string;
  sourceUrl: string;
  pageNumber?: number;
  exactQuote: string;
  publisherFamily: string;
  sourceTier: number;
  reportedAt?: string;
};
```

Before a fact enters the evidence ledger, its quote must be found verbatim or through a controlled normalized comparison in the fetched document. Unverified facts are dropped from final reporting.

### 6.4 Calculation engine

All arithmetic occurs in deterministic application code. The AI model may explain calculations but must not be the source of numeric computation.

Initial calculations include period-over-period growth, CAGR, GNPA and NNPA changes, slippage ratio, credit cost, provision coverage, write-off-adjusted asset quality, AUM or loan-book growth, off-book share, funding concentration, funding-mix change, CASA change, NIM change, yield minus cost of funds, peer-relative z-score, persistence score, and narrative-to-metric divergence.

Each calculation stores its formula, result, unit, input fact IDs, and interpretation.

### 6.5 Investigation lenses

1. Narrative versus numbers
2. Segment versus aggregate
3. Company versus peers
4. Entity versus counterparty
5. Stock versus flow
6. Funding dependency
7. Disclosure drift

### 6.6 Hypothesis generation

The system generates at least three candidate hypotheses per run. Each includes a claim, mechanism, relevant metrics, supporting facts, opposing facts, timeline, alternative explanation, evidence score, and status.

The ranker selects the strongest surviving hypothesis rather than presenting the first generated idea.

### 6.7 Contradiction detection

Contradictions are typed and visible:

- Restatement or comparative-period mismatch
- Investor-presentation versus filing mismatch
- Segment total versus reported aggregate mismatch
- Guidance versus later actual results
- Narrative versus metric mismatch
- Definition or disclosure drift
- Company versus counterparty mismatch
- Company versus peer mismatch

### 6.8 Self-falsification

The leading hypothesis runs five tests:

1. Sector test: do most peers show the same divergence?
2. Accounting-artifact test: could a merger, consolidation, write-off, or definition change explain it?
3. Base-effect test: does it survive two-year and three-year comparisons?
4. Regulatory or macro test: does timing align with an RBI action, rate cycle, or industry event?
5. Disclosure-change test: did the company change what it reports?

The dashboard shows PASS, FAIL, or INCONCLUSIVE with evidence. If a hypothesis fails materially, the system moves to the next candidate.

## 7. AI and external API design

### 7.1 API-key principles

- API keys are server-side only.
- No API key is sent to the browser.
- No key is hard-coded.
- Keys are supplied through environment variables.
- `.env.example` contains variable names only.
- Logs redact key values.
- Offline mode works without API keys.
- Providers are replaceable.

### 7.2 AI provider configuration

The initial provider abstraction supports OpenAI-compatible APIs and can later support Gemini or other providers.

```env
AI_PROVIDER=openai
AI_MODEL=
OPENAI_API_KEY=
OPENAI_BASE_URL=
GEMINI_API_KEY=
```

The selected provider is called only on the server.

The AI may create research plans, classify passages, map passages to known metrics, generate hypotheses, explain calculated divergences, generate counterarguments, propose falsification conditions, and produce final prose from validated facts.

The AI may not invent source URLs, invent citations, perform unverified arithmetic, introduce unsourced numbers, override deterministic calculations, treat unsupported claims as facts, decide source independence without metadata, or suppress contradictory evidence.

All model outputs are validated against runtime schemas.

### 7.3 Search API configuration

The search layer supports a configurable provider:

```env
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=
SERPER_API_KEY=
```

Search results must return structured source metadata. The AI may select from returned results but cannot create new URLs.

If no search API is configured, offline fixture mode remains available and direct official-source adapters may still run with reduced coverage.

### 7.4 AI execution flow

```text
1. Deterministic resolver finds company and peers.
2. Source collector fetches documents.
3. Parser extracts text and tables.
4. Deterministic normalizer creates candidate facts.
5. AI classifies and structures ambiguous passages.
6. Deterministic calculation engine computes metrics.
7. Deterministic divergence detector ranks anomalies.
8. AI generates hypotheses from ranked anomalies.
9. Source collector searches for support and opposition.
10. Deterministic contradiction and falsification tests run.
11. AI explains the final validated discovery.
12. Runtime validation checks the final object.
13. Dashboard renders only validated data.
```

## 8. Technical stack

### Frontend

- Semantic HTML
- CSS custom properties and responsive CSS
- Vanilla browser JavaScript modules
- SVG charts and native accessible controls

The first vertical slice intentionally avoids a frontend build dependency so that the app can run offline in the hackathon environment. The visual system still follows the dashboard requirements in this document and can be migrated to a component framework later without changing the research contracts.

### Backend

- Python 3.12 standard-library HTTP server
- JSON API endpoints
- Python service modules
- SQLite-compatible persistence boundary
- Server-side source adapters
- Local document cache

### Validation

- Python dataclasses and explicit validation functions
- JSON shape validation at API boundaries
- Structured AI outputs when a provider is configured

### Document processing

- Standard-library HTML parsing foundation
- Pluggable PDF text extraction adapter
- Page-preserving document representation
- Exact quote verification

### Storage

SQLite tables:

```text
runs
companies
documents
facts
calculations
hypotheses
contradictions
falsification_tests
evidence_links
events
```

### Testing

- Python `unittest`
- Fixture-based end-to-end tests
- Calculation unit tests
- Schema validation tests
- Source citation tests
- Research pipeline smoke tests

### Build and deployment

- Dockerfile based on Python 3.12.8
- `.python-version` runtime pin
- `requirements.lock` dependency lockfile
- README with exact setup instructions
- One canonical offline test command

## 9. Project structure

```text
signal-lens/
├── app.py
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── signal_lens/
│   ├── models.py
│   ├── resolver.py
│   ├── calculations.py
│   └── engine.py
├── fixtures/
│   └── research-run/
├── tests/
├── Dockerfile
├── README.md
├── .env.example
├── requirements.txt
└── requirements.lock
```

## 10. HTTP API

Planned server routes:

```text
POST /api/resolve
POST /api/research
GET  /api/runs/:runId
GET  /api/runs/:runId/events
GET  /api/runs/:runId/evidence
GET  /api/runs/:runId/report
POST /api/runs/:runId/replay
```

All inputs are validated server-side. Long-running research should use a persisted run record so the result can be reloaded after navigation or refresh.

## 11. Offline fixture mode

Offline mode is required for development, automated tests, demo reliability, no-key environments, and API outage recovery.

The fixture corpus contains sample company identity, peer identities, source metadata, page-tagged document text, structured facts, calculations, candidate hypotheses, contradictory evidence, falsification results, and a final discovery.

Fixture mode must exercise the same report and dashboard code used by live mode and must be clearly labeled as fixture/demo data.

## 12. Security and privacy

- No login or personal account data.
- No API keys in client bundles.
- No secrets in source control.
- No credentials in logs.
- Only public information may be fetched.
- User input is validated.
- External URLs are untrusted content.
- Downloaded documents are stored outside the public web directory.
- Search results are sanitized before display.
- Source links open safely.

## 13. Error handling

The application must distinguish invalid input, partial source failure, weak evidence, unavailable AI provider, unavailable search provider, and no defensible discovery.

The system must be allowed to return:

> No strong discovery found.

This is preferable to inventing a conclusion.

## 14. Testing requirements

### Unit tests

- Company input normalization
- Business-model classification
- Growth calculations
- Asset-quality calculations
- Peer comparison
- Divergence scoring
- Falsification scoring
- Evidence-strength classification
- Exact quote verification
- Schema validation

### Integration tests

- Offline source collection
- Offline fact extraction
- Full offline research run
- Persistence and replay
- Results dashboard data loading
- Invalid-company handling

### Acceptance test

A complete offline run must load the fixture company, resolve it, load peers, extract facts, compute derived metrics, generate at least three hypotheses, reject or downgrade at least one hypothesis, produce supporting and opposing evidence, run falsification tests, render all eight report sections, persist the result, and reload the result from storage.

## 15. Milestones

### Milestone 1: Repository foundation

- Initialize Git
- Create package manifest and lockfile
- Pin runtime
- Add Dockerfile
- Add README
- Add environment template
- Add testing setup

### Milestone 2: Landing page

- Build no-login landing page
- Add company input
- Add Track A explanation
- Add loading and invalid-input states

### Milestone 3: Research schemas and offline engine

- Add schemas
- Add fixture corpus
- Add calculations
- Add hypothesis and discovery models
- Add test command

### Milestone 4: Complete offline vertical slice

- Landing page
- Research progress
- Offline investigation
- Results dashboard
- Evidence ledger
- Timeline
- Counterargument
- Falsification panel

### Milestone 5: Public source adapters

- Add source discovery
- Add document caching
- Add PDF/HTML parsing
- Add quote verification
- Add source tiers

### Milestone 6: AI provider integration

- Add provider abstraction
- Add structured model calls
- Add prompt templates
- Add retries and fallback
- Add token and cost logging without exposing secrets

### Milestone 7: Live research hardening

- Test unseen companies
- Improve resolver
- Improve peer selection
- Add partial-source handling
- Add replay mode
- Add source coverage warnings

### Milestone 8: Demo readiness

- Add print/export view
- Add rejected hypotheses
- Add research logs
- Run Docker build
- Run all tests
- Prepare a cached successful run
- Test a cold run on an unseen company

## 16. Definition of done

SignalLens is ready for the hackathon demo when:

- The app starts without login.
- The landing page communicates the product within seconds.
- A company can be entered by name or symbol.
- The app can perform a complete offline research run.
- A live research mode exists behind optional API configuration.
- The output contains all eight required sections.
- Calculations are deterministic and inspectable.
- Claims link to source documents and exact passages.
- Supporting and contradictory evidence are visible.
- At least one hypothesis can be rejected.
- Falsification tests display PASS, FAIL, or INCONCLUSIVE results.
- The system can process a different supported Track A company without changing company-specific logic.
- The application builds from a clean Docker environment.
- The repository contains a lockfile, README, Dockerfile, `.env.example`, and offline test command.
- No secrets or machine-specific paths are committed.
