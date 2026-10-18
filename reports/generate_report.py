"""Generate the two-page AlphaTrace Round 1 solution report.

The report deliberately uses a tiny standard-library PDF writer so the artifact
can be rebuilt in the same offline environment as the application.  It is not
intended to be a general document engine; its layout is fixed to this report's
two A4 pages and its text is kept in this file for reviewability.
"""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import wrap
from urllib.parse import quote


PAGE_W = 595.28
PAGE_H = 841.89
MARGIN = 38.0
INK = (0.10, 0.13, 0.16)
MUTED = (0.34, 0.39, 0.43)
LIGHT = (0.91, 0.92, 0.91)
PALE = (0.965, 0.97, 0.965)
ACCENT = (0.08, 0.36, 0.34)
ACCENT_LIGHT = (0.86, 0.93, 0.91)
WARM = (0.96, 0.94, 0.89)


def ascii_safe(value: str) -> str:
    """Keep the built-in Helvetica encoding predictable and portable."""

    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2192": "->",
        "\u2190": "<-",
        "\u2194": "<->",
        "\u2022": "-",
        "\u00b7": "|",
        "\u00d7": "x",
        "\u2265": ">=",
        "\u2264": "<=",
        "\u00a0": " ",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value.encode("latin-1", "replace").decode("latin-1")


def pdf_escape(value: str) -> str:
    return ascii_safe(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def colour(rgb: tuple[float, float, float]) -> str:
    return " ".join(f"{component:.3f}" for component in rgb)


class Canvas:
    """Small content-stream helper using top-origin coordinates."""

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.links: list[tuple[float, float, float, float, str]] = []

    def _y(self, top: float) -> float:
        return PAGE_H - top

    def fill(self, x: float, top: float, width: float, height: float, rgb: tuple[float, float, float]) -> None:
        self.commands.extend([f"{colour(rgb)} rg", f"{x:.2f} {self._y(top + height):.2f} {width:.2f} {height:.2f} re f"])

    def stroke_rect(self, x: float, top: float, width: float, height: float, rgb: tuple[float, float, float], line_width: float = 0.6) -> None:
        self.commands.extend([f"{colour(rgb)} RG", f"{line_width:.2f} w", f"{x:.2f} {self._y(top + height):.2f} {width:.2f} {height:.2f} re S"])

    def line(self, x1: float, top1: float, x2: float, top2: float, rgb: tuple[float, float, float] = LIGHT, line_width: float = 0.6) -> None:
        self.commands.extend([f"{colour(rgb)} RG", f"{line_width:.2f} w", f"{x1:.2f} {self._y(top1):.2f} m {x2:.2f} {self._y(top2):.2f} l S"])

    def text(self, x: float, top: float, value: str, size: float = 8.2, font: str = "F1", rgb: tuple[float, float, float] = INK) -> float:
        self.commands.extend([
            f"{colour(rgb)} rg",
            "BT",
            f"/{font} {size:.2f} Tf",
            f"{x:.2f} {self._y(top + size):.2f} Td",
            f"({pdf_escape(value)}) Tj",
            "ET",
        ])
        return size

    def link(self, x: float, top: float, width: float, height: float, url: str) -> None:
        self.links.append((x, PAGE_H - top - height, x + width, PAGE_H - top, url))

    @staticmethod
    def text_width(value: str, size: float) -> float:
        # Helvetica's average glyph width is close enough for wrapping, while
        # keeping the generator independent of font metric packages.
        return len(ascii_safe(value)) * size * 0.49

    def wrapped(self, x: float, top: float, value: str, width: float, size: float = 8.2, leading: float = 10.2, font: str = "F1", rgb: tuple[float, float, float] = INK, max_lines: int | None = None) -> float:
        paragraphs = value.split("\n")
        lines: list[str] = []
        max_chars = max(1, int(width / (size * 0.49)))
        for paragraph in paragraphs:
            if not paragraph.strip():
                lines.append("")
                continue
            lines.extend(wrap(ascii_safe(paragraph), width=max_chars, break_long_words=False, break_on_hyphens=False))
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            if lines:
                lines[-1] = lines[-1].rstrip(" .") + "..."
        for index, line in enumerate(lines):
            self.text(x, top + index * leading, line, size, font, rgb)
        return top + len(lines) * leading

    def bullet_list(self, x: float, top: float, items: list[str], width: float, size: float = 7.8, leading: float = 9.2, gap: float = 1.5, bullet_rgb: tuple[float, float, float] = ACCENT) -> float:
        current = top
        for item in items:
            self.text(x, current, "-", size, "F2", bullet_rgb)
            current = self.wrapped(x + 10, current, item, width - 10, size, leading, "F1", INK)
            current += gap
        return current

    def section_label(self, x: float, top: float, value: str, width: float | None = None) -> None:
        self.text(x, top, value.upper(), 6.7, "F2", ACCENT)
        if width:
            self.line(x + self.text_width(value.upper(), 6.7) + 8, top + 4.2, x + width, top + 4.2, LIGHT, 0.5)


class Pdf:
    def __init__(self) -> None:
        self.objects: list[bytes] = []
        self.pages: list[tuple[bytes, list[tuple[float, float, float, float, str]]]] = []

    def add_page(self, canvas: Canvas) -> None:
        content = "\n".join(canvas.commands).encode("latin-1")
        self.pages.append((content, canvas.links))

    def _add_object(self, body: bytes) -> int:
        self.objects.append(body)
        return len(self.objects)

    def build(self) -> bytes:
        font_regular = self._add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font_bold = self._add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        font_italic = self._add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>")
        page_tree = self._add_object(b"<< /Type /Pages /Kids [] /Count 0 >>")
        page_ids: list[int] = []
        for content, links in self.pages:
            stream = f"<< /Length {len(content)} >>\nstream\n".encode("latin-1") + content + b"\nendstream"
            content_id = self._add_object(stream)
            annotation_ids: list[int] = []
            for x1, y1, x2, y2, url in links:
                uri = pdf_escape(url)
                annotation_ids.append(self._add_object(f"<< /Type /Annot /Subtype /Link /Rect [{x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f}] /Border [0 0 0] /A << /S /URI /URI ({uri}) >> >>".encode("latin-1")))
            annots = f" /Annots [{ ' '.join(f'{item} 0 R' for item in annotation_ids) }]" if annotation_ids else ""
            page_id = self._add_object(
                f"<< /Type /Page /Parent {page_tree} 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] /Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R /F3 {font_italic} 0 R >> >> /Contents {content_id} 0 R{annots} >>".encode("latin-1")
            )
            page_ids.append(page_id)
        kids = " ".join(f"{item} 0 R" for item in page_ids)
        self.objects[page_tree - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
        catalog = self._add_object(f"<< /Type /Catalog /Pages {page_tree} 0 R >>".encode("latin-1"))

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(self.objects, start=1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("latin-1"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref = len(output)
        output.extend(f"xref\n0 {len(self.objects) + 1}\n".encode("latin-1"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        output.extend(f"trailer\n<< /Size {len(self.objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1"))
        return bytes(output)


def top_header(canvas: Canvas, page_label: str, title: str, subtitle: str) -> float:
    canvas.text(MARGIN, 30, "ATMOS 2026  |  BITS PILANI, HYDERABAD CAMPUS  |  ROUND 1", 6.7, "F2", ACCENT)
    canvas.text(MARGIN, 47, title, 20.5, "F2", INK)
    canvas.text(MARGIN, 73, subtitle, 9.2, "F3", MUTED)
    canvas.fill(PAGE_W - MARGIN - 118, 39, 118, 42, ACCENT)
    canvas.text(PAGE_W - MARGIN - 106, 51, "TRACK A", 7.2, "F2", (1.0, 1.0, 1.0))
    canvas.text(PAGE_W - MARGIN - 106, 64, "BANKING | NBFCs | FINANCIAL SERVICES", 5.2, "F1", (0.89, 0.96, 0.94))
    canvas.line(MARGIN, 92, PAGE_W - MARGIN, 92, LIGHT, 0.8)
    canvas.text(PAGE_W - MARGIN - 45, PAGE_H - 22, page_label, 6.5, "F2", MUTED)
    return 105


def draw_page_one() -> Canvas:
    c = Canvas()
    top_header(c, "01 / 02", "AlphaTrace", "An evidence-first autonomous financial research investigator")

    c.section_label(MARGIN, 106, "The idea", 300)
    c.wrapped(MARGIN, 119, "Given only a NIFTY 50 company, AlphaTrace decides which financial relationships are worth investigating. It turns public filings, peer disclosures and independent sector evidence into one auditable discovery - not a finance chatbot, news summary or investment recommendation.", 302, 8.15, 10.2, "F1", INK)
    c.wrapped(MARGIN, 170, "The problem is fragmentation: a company can describe improving asset quality while the flow of stress, its peers, or an external source tells a different story. A single-document summariser cannot reliably expose that relationship.", 302, 8.15, 10.2, "F1", MUTED)

    x = 363.0
    c.fill(x, 106, 194, 86, ACCENT)
    c.text(x + 13, 118, "COMPUTE-FIRST DIFFERENTIATOR", 6.7, "F2", (0.86, 0.96, 0.93))
    c.wrapped(x + 13, 133, "The pipeline computes a time-indexed grid of metrics first, detects a divergence second, and asks the model to explain only validated patterns. The anomaly is found by arithmetic; prose cannot invent the number or URL.", 168, 8.0, 9.8, "F1", (1.0, 1.0, 1.0))

    c.section_label(MARGIN, 218, "Research pipeline", PAGE_W - MARGIN)
    c.wrapped(MARGIN, 231, "The same sequential coordinator drives offline fixtures and live public-source runs. Each stage emits inspectable artefacts; rejected hypotheses and missing coverage remain visible.", PAGE_W - 2 * MARGIN, 7.7, 9.2, "F1", MUTED)

    boxes = [
        ("1  INPUT + RESOLVE", "Company / symbol -> identity, model, peers"),
        ("2  PLAN", "Metric pack, periods, source queries"),
        ("3  DISCOVER", "Candidate filings, peers, RBI, ratings"),
        ("4  VERIFY", "Fetch, parse, normalize, quote-check"),
        ("5  CALCULATE", "Derived ratios and divergence scores"),
        ("6  HYPOTHESIZE", "Competing explanations with evidence IDs"),
        ("7  CHALLENGE", "Independent corroboration + conflicts"),
        ("8  REPORT", "Falsify, rank, validate, render"),
    ]
    box_x = MARGIN
    box_w = 122.0
    box_h = 38.0
    gap = 8.0
    for index, (label, detail) in enumerate(boxes):
        row, col = divmod(index, 4)
        bx = box_x + col * (box_w + gap)
        by = 274 + row * 58
        c.fill(bx, by, box_w, box_h, PALE if index not in {4, 7} else ACCENT_LIGHT)
        c.stroke_rect(bx, by, box_w, box_h, ACCENT if index in {4, 7} else LIGHT, 0.8)
        c.text(bx + 7, by + 7, label, 6.1, "F2", ACCENT if index in {4, 7} else INK)
        c.wrapped(bx + 7, by + 18, detail, box_w - 14, 6.6, 7.7, "F1", MUTED, max_lines=2)
        if col < 3:
            c.text(bx + box_w + 1.5, by + 15, ">", 9, "F2", ACCENT)
    c.line(MARGIN + 3 * (box_w + gap) + box_w / 2, 312, MARGIN + 3 * (box_w + gap) + box_w / 2, 332, ACCENT, 0.8)
    c.text(MARGIN + 3 * (box_w + gap) + box_w / 2 - 3, 319, "v", 7, "F2", ACCENT)
    c.line(MARGIN + box_w / 2, 370, MARGIN + box_w / 2, 389, ACCENT, 0.8)
    c.text(MARGIN + box_w / 2 - 3, 375, "v", 7, "F2", ACCENT)
    c.text(MARGIN + 185, 393, "If evidence is insufficient, return to planning or report: No strong discovery found.", 6.8, "F3", MUTED)

    left_x = MARGIN
    right_x = 319.0
    c.section_label(left_x, 425, "Discovery mechanism", 252)
    c.wrapped(left_x, 438, "The first Track A pack asks whether headline asset-quality improvement is supported by the underlying flow of stress. The lens library is reusable; the resolver selects the applicable pack for Bank, NBFC, Insurer or Holdco.", 252, 7.7, 9.1, "F1", INK)
    c.bullet_list(left_x, 487, [
        "Stock vs flow: GNPA with NNPA, write-offs, credit cost or provision coverage.",
        "Self vs peer: distinguish a company-specific signal from sector normalization.",
        "Narrative vs number, segment vs aggregate, and entity vs counterparty where data permits.",
        "Temporal persistence: align periods, detect when the relationship changed, and test base effects.",
    ], 252, 7.35, 8.5, 1.2)

    c.section_label(right_x, 425, "Confirmed now / finals next", 238)
    c.fill(right_x, 438, 238, 116, WARM)
    c.stroke_rect(right_x, 438, 238, 116, (0.88, 0.84, 0.75), 0.6)
    c.text(right_x + 10, 450, "CONFIRMED IN REPOSITORY", 6.4, "F2", ACCENT)
    c.bullet_list(right_x + 10, 462, [
        "Offline end-to-end research engine and dashboard.",
        "Deterministic calculations, typed report objects, claim ledger and SQLite replay.",
        "Public URL validation, bounded retrieval/cache, page-aware parsing and quote verification.",
        "Conservative live mode that downgrades or withholds weak findings.",
    ], 218, 7.1, 8.2, 0.8)
    c.text(right_x + 10, 568, "FINALS WORK", 6.4, "F2", ACCENT)
    c.wrapped(right_x + 10, 579, "Broaden peer/source coverage, metric packs and cold unseen-company validation; keep every limitation explicit.", 218, 7.2, 8.6, "F1", MUTED)

    c.line(MARGIN, 665, PAGE_W - MARGIN, 665, LIGHT, 0.8)
    c.text(MARGIN, 677, "Design rule: deterministic code owns arithmetic, source identity, quote status, independence metadata, conflict classification and final schema validation.", 7.1, "F3", MUTED)
    c.text(MARGIN, 698, "Public sources only  |  No investment recommendations  |  Company-specific conclusions are never hard-coded", 6.8, "F2", ACCENT)
    c.text(MARGIN, PAGE_H - 22, "ALPHATRACE  |  TRACK A  |  IDEA + ARCHITECTURE", 6.5, "F2", MUTED)
    return c


def draw_page_two() -> Canvas:
    c = Canvas()
    top_header(c, "02 / 02", "Make every conclusion contestable", "Evidence triangulation, output contract, generalisation and delivery plan")

    left_x = MARGIN
    right_x = 331.0
    left_w = 278.0
    right_w = 226.0
    c.section_label(left_x, 106, "Evidence + contradiction", left_x + left_w)
    c.wrapped(left_x, 119, "Search results are candidates, not evidence. A source enters the ledger only after public-URL validation, bounded retrieval, parsing and exact or controlled-normalized quote verification.", left_w, 7.75, 9.25, "F1", INK)
    c.bullet_list(left_x, 165, [
        "Every fact stores metric, value, unit, period, scope, source URL, publisher family, tier, page and exact passage.",
        "Every claim points to evidence IDs and calculation IDs; displayed numbers come from deterministic Python code.",
        "Independent-family count prevents three company-authored documents from masquerading as three confirmations.",
        "Typed conflicts surface narrative/metric, restatement, scope, timing and company/peer mismatches instead of hiding them.",
    ], left_w, 7.35, 8.55, 1.0)
    c.text(left_x, 237, "Evidence ladder", 6.6, "F2", ACCENT)
    sources = [
        ("T1", "NSE/BSE filings, results, annual reports", "https://www.nseindia.com/"),
        ("T2", "Investor presentations and earnings calls", "https://www.bseindia.com/"),
        ("T3", "RBI / IRDAI / SEBI independent data", "https://www.rbi.org.in/"),
        ("T4-T6", "Ratings, peers, counterparties, credible media", "https://www.crisilratings.com/"),
    ]
    sy = 250
    for tier, label, url in sources:
        c.text(left_x, sy, tier, 6.6, "F2", ACCENT)
        c.text(left_x + 30, sy, label, 7.0, "F1", INK)
        c.link(left_x + 30, sy - 1, min(left_w - 30, c.text_width(label, 7.0)), 9, url)
        sy += 13

    c.section_label(right_x, 106, "Self-falsification", PAGE_W - MARGIN)
    c.fill(right_x, 119, right_w, 174, ACCENT)
    c.text(right_x + 12, 132, "The leading hypothesis must earn its rating", 8.0, "F2", (1.0, 1.0, 1.0))
    tests = [
        ("T1", "Sector", "Do most peers show the same divergence?"),
        ("T2", "Accounting", "Could scope, M&A or definition drift explain it?"),
        ("T3", "Base effect", "Does it survive two- and three-year views?"),
        ("T4", "Macro / regulatory", "Does timing align with an industry event?"),
        ("T5", "Disclosure change", "Did the company change what it reports?"),
    ]
    ty = 151
    for code, name, question in tests:
        c.text(right_x + 12, ty, code, 6.6, "F2", (0.72, 0.90, 0.86))
        c.text(right_x + 32, ty, name, 6.8, "F2", (1.0, 1.0, 1.0))
        c.wrapped(right_x + 32, ty + 9, question, right_w - 44, 6.7, 7.5, "F1", (0.90, 0.96, 0.94), max_lines=2)
        ty += 27
    c.text(right_x + 12, 278, "PASS / FAIL / INCONCLUSIVE is evidence, not decoration.", 6.5, "F3", (0.82, 0.94, 0.91))

    c.section_label(MARGIN, 318, "Illustrative final report object", PAGE_W - MARGIN)
    c.wrapped(MARGIN, 331, "The renderer receives one validated object with all eight required elements. The sketch below shows the shape, not a researched company result or fabricated figure.", PAGE_W - 2 * MARGIN, 7.5, 8.9, "F1", MUTED)
    wire_x, wire_y, wire_w, wire_h = MARGIN, 363, PAGE_W - 2 * MARGIN, 167
    c.fill(wire_x, wire_y, wire_w, wire_h, PALE)
    c.stroke_rect(wire_x, wire_y, wire_w, wire_h, LIGHT, 0.7)
    cell_w = (wire_w - 24) / 2
    cell_h = 36
    cells = [
        ("1  DISCOVERY", "[one clear non-obvious finding]"),
        ("2  WHY IT MATTERS", "[3-5 significance bullets]"),
        ("3  EVIDENCE", "[independent sources + clickable links]"),
        ("4  TIMELINE", "[when the change emerged]"),
        ("5  NUMBERS", "[formula -> inputs -> result]"),
        ("6  COUNTERARGUMENT", "[strongest alternative / conflict]"),
        ("7  FALSIFICATION", "[future condition that changes view]"),
        ("8  STRENGTH", "[Strong / Moderate / Weak + why]"),
    ]
    for index, (label, detail) in enumerate(cells):
        row, col = divmod(index, 2)
        cx = wire_x + 8 + col * (cell_w + 8)
        cy = wire_y + 8 + row * (cell_h + 4)
        c.fill(cx, cy, cell_w, cell_h, (1.0, 1.0, 1.0))
        c.stroke_rect(cx, cy, cell_w, cell_h, LIGHT, 0.5)
        c.text(cx + 7, cy + 6, label, 6.2, "F2", ACCENT)
        c.wrapped(cx + 7, cy + 17, detail, cell_w - 14, 6.8, 8.0, "F3", MUTED, max_lines=2)
    c.text(wire_x + 8, 536, "A click on any major claim opens its document, page, passage, period and calculation trace.", 6.8, "F3", ACCENT)

    gen_x = MARGIN
    gen_y = 557
    gen_w = 278.0
    stack_x = 331.0
    stack_w = 226.0
    c.section_label(gen_x, gen_y, "Generality", gen_x + gen_w)
    c.wrapped(gen_x, gen_y + 13, "Constants: typed schemas, source policy, quote checks, calculation engine, conflict types, five tests and report contract. Dynamic at runtime: company identity, business model, peers, periods, source plan, metric pack and hypotheses.", gen_w, 7.55, 9.0, "F1", INK)
    c.wrapped(gen_x, gen_y + 78, "A resolver classifies Bank / NBFC / Insurer / Holdco and selects a compatible pack. Missing disclosures reduce evidence strength or stop a conclusion; a new company does not require a new answer template.", gen_w, 7.55, 9.0, "F1", MUTED)

    c.section_label(stack_x, stack_y := gen_y, "Tools + data", PAGE_W - MARGIN)
    c.fill(stack_x, stack_y + 13, stack_w, 93, PALE)
    c.text(stack_x + 10, stack_y + 25, "STACK", 6.4, "F2", ACCENT)
    c.wrapped(stack_x + 10, stack_y + 37, "Python 3.12.8; explicit sequential coordinator; vanilla HTML/CSS/JS; SQLite; standard-library HTTP/HTML parsing; Docker Poppler boundary for PDFs; optional Tavily search and structured OpenAI-compatible provider.", stack_w - 20, 7.05, 8.35, "F1", INK)
    c.text(stack_x + 10, stack_y + 83, "No multi-agent framework is required to make the trail auditable.", 6.5, "F3", MUTED)

    c.section_label(MARGIN, 685, "Build plan to finals", PAGE_W - MARGIN)
    milestones = [
        ("18-19 OCT", "Freeze Round 1 report; run offline end-to-end checks; review source and limitation wording."),
        ("20-21 OCT", "Broaden peer retrieval and independent-family scoring; extend bank/NBFC/insurer metric coverage."),
        ("22 OCT", "Harden temporal alignment, typed contradictions and five falsification tests; preserve weak-result fallback."),
        ("23-24 OCT", "Cold-run unseen NIFTY 50 and other listed Track A companies; Docker build; cache a recovery run; rehearse demo."),
        ("25 OCT", "Finals: live judge-selected company, discovery, evidence trail, counterargument and falsification condition."),
    ]
    my = 700
    for label, detail in milestones:
        c.text(MARGIN, my, label, 6.6, "F2", ACCENT)
        c.wrapped(MARGIN + 74, my, detail, PAGE_W - 2 * MARGIN - 74, 7.1, 8.2, "F1", INK, max_lines=1)
        c.line(MARGIN, my + 14, PAGE_W - MARGIN, my + 14, LIGHT, 0.45)
        my += 22
    c.text(MARGIN, PAGE_H - 22, "ALPHATRACE  |  TRACK A  |  ALPHATRACE_TRACKA_ROUND1.PDF  |  PUBLIC SOURCES ONLY", 6.3, "F2", MUTED)
    return c


def generate(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = Pdf()
    pdf.add_page(draw_page_one())
    pdf.add_page(draw_page_two())
    output.write_bytes(pdf.build())
    return output


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "AlphaTrace_TrackA_Round1.pdf"
    print(generate(target))
