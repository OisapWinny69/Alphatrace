# AlphaTrace

AlphaTrace is a no-login autonomous financial research dashboard for the ATMOS 2026 **Track A — Banking, NBFCs & Financial Services** challenge.

It is designed around a compute-first research flow:

```text
Company → facts → calculations → divergences → hypotheses → falsification → discovery
```

The current vertical slice is intentionally dependency-free Python so it can run offline and remain reliable during a demo. It includes a polished browser dashboard, a fixture-backed research engine, deterministic calculations, source-linked evidence cards, a timeline, counterarguments, and falsification tests.

## Requirements

- Python 3.12+
- No global package installation is required.

## Run locally

```bash
python app.py
```

Then open <http://127.0.0.1:8000>.

The app starts in offline mode by default. Enter a supported symbol such as `HDFCBANK`, `BAJFINANCE`, or `SHRIRAMFIN` and start an investigation.

## Run the tests

```bash
make test
```

The test suite is offline and verifies the resolver, deterministic calculations, hypothesis ranking, falsification logic, and the complete research pipeline.

The complete implementation strategy, judging-rubric mapping, source policy,
auditability contracts, and delivery gates are in [`HACKATHON_PLAN.md`](HACKATHON_PLAN.md).

## Configuration

Copy `.env.example` to `.env` for local configuration. The current offline vertical slice does not need API keys. Future live adapters will read provider keys only on the server:

- `OPENAI_API_KEY` or `GEMINI_API_KEY` for structured research reasoning
- `TAVILY_API_KEY` or `SERPER_API_KEY` for public web discovery

Keys must never be put into browser code, source control, or logs.

Live-source boundaries are implemented with the standard library in
`alpha_trace/sources.py`: candidate search results are separated from fetched
documents, public URLs are validated, documents are cached outside `static/`,
HTML is parsed into visible text, and quotes are marked `verified`,
`normalized_match`, or `failed`. PDF parsing remains an explicit adapter
boundary so unverifiable PDF claims are not silently promoted to evidence.

## Docker

```bash
docker build -t alphatrace .
docker run --rm -p 8000:8000 alphatrace
```

Open <http://127.0.0.1:8000> after the container starts.

## Project structure

```text
.
├── app.py                         # stdlib HTTP server and JSON API
├── alpha_trace/
│   ├── calculations.py            # deterministic financial math
│   ├── engine.py                  # offline autonomous research pipeline
│   ├── models.py                  # typed dataclasses and serialization
│   └── resolver.py                # company and peer resolution
├── static/
│   ├── index.html                 # no-login landing and dashboard shell
│   ├── app.js                     # browser workflow and rendering
│   └── styles.css                 # responsive dark research UI
├── tests/
├── PRD.md
├── Dockerfile
├── .env.example
├── .python-version
├── requirements.txt
└── requirements.lock
```

## Research integrity rules

- Arithmetic is performed by Python, never by the model.
- Source URLs come from source metadata, never from generated prose.
- Evidence cards include source, period, quote, and evidence role.
- The UI labels the current fixture mode clearly.
- Weak evidence may produce “No strong discovery found” rather than an invented conclusion.
- The product does not provide investment recommendations.

## Roadmap

The next milestones are live public-source adapters, page-preserving PDF extraction, exact quote verification, optional structured AI reasoning, peer corpus expansion, SQLite run persistence, and live cold-run testing on an unseen company. The product requirements and security boundaries are documented in `PRD.md`.
