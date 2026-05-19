"""
Power Profile PDF renderer (Week 6 C.5 of the 2026-05-04 launch roadmap).

Produces a 3-page printable employer briefing for union organizers:
    Page 1 -- Identity & Money
    Page 2 -- Workforce & Enforcement
    Page 3 -- Network & Risk

The router (`api/routers/power_profile.py`) is responsible for ALL data
aggregation. This module is presentation-only: it takes a fully populated
`payload` dict and emits a PDF to a file-like object. Keeping queries in
the router means the renderer can be unit-tested with synthetic payloads
and never touches the DB.

Design choices:
- ReportLab platypus (Frame + Paragraph + Table) over a raw Canvas, so
  long fields wrap cleanly and tables size themselves.
- Built-in Helvetica only (no font registration; avoids Windows path
  fragility).
- 0.6" margins, 7-9pt text -- "dense organizer-friendly" is the brief.
- Sections that have no data still render the header + a "No data
  available" line; we never blank-out a section because an organizer
  reading the printed PDF needs to know they SAW the data was absent
  rather than wonder if the form was clipped.

PDFs land at ~30-60 KB for typical inputs (well under the 100 KB target).
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ----- styling -----------------------------------------------------------

_PAGE_W, _PAGE_H = LETTER
_LEFT_MARGIN = 0.6 * inch
_RIGHT_MARGIN = 0.6 * inch
_TOP_MARGIN = 0.55 * inch
_BOTTOM_MARGIN = 0.55 * inch
_USABLE_WIDTH = _PAGE_W - _LEFT_MARGIN - _RIGHT_MARGIN  # ~7.3"

_styles = getSampleStyleSheet()
_BODY = ParagraphStyle(
    "PpBody",
    parent=_styles["Normal"],
    fontName="Helvetica",
    fontSize=8.5,
    leading=10.5,
    spaceBefore=0,
    spaceAfter=0,
)
_BODY_SMALL = ParagraphStyle(
    "PpBodySmall",
    parent=_BODY,
    fontSize=7.5,
    leading=9,
)
_H1 = ParagraphStyle(
    "PpH1",
    parent=_styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=15,
    leading=18,
    spaceBefore=0,
    spaceAfter=4,
    textColor=colors.HexColor("#0B2547"),
)
_H2 = ParagraphStyle(
    "PpH2",
    parent=_styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=10.5,
    leading=13,
    spaceBefore=8,
    spaceAfter=2,
    textColor=colors.HexColor("#0B2547"),
)
_LABEL = ParagraphStyle(
    "PpLabel",
    parent=_BODY,
    fontName="Helvetica-Bold",
    fontSize=7.5,
    leading=9,
    textColor=colors.HexColor("#444444"),
)
_NA = ParagraphStyle(
    "PpNA",
    parent=_BODY_SMALL,
    textColor=colors.HexColor("#888888"),
)


_TABLE_BASE_STYLE = TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    ("LEADING", (0, 0), (-1, -1), 9.5),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#0B2547")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
])

_TIER_COLORS = {
    "platinum": colors.HexColor("#5C4D7D"),
    "gold": colors.HexColor("#B8860B"),
    "silver": colors.HexColor("#7B8794"),
    "bronze": colors.HexColor("#A0522D"),
    "Strong": colors.HexColor("#1B5E20"),
    "Promising": colors.HexColor("#2E7D32"),
    "Speculative": colors.HexColor("#EF6C00"),
    "Watchlist": colors.HexColor("#757575"),
}


# ----- formatting helpers -----------------------------------------------

def _fmt_money(v: Optional[float], short: bool = True) -> str:
    """Format a USD amount. `short` -> $1.23M / $456K. None -> '--'."""
    if v is None:
        return "--"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "--"
    if n == 0:
        return "$0"
    if not short:
        return f"${n:,.0f}"
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if abs_n >= 1_000_000_000:
        return f"{sign}${abs_n / 1_000_000_000:.1f}B"
    if abs_n >= 1_000_000:
        return f"{sign}${abs_n / 1_000_000:.1f}M"
    if abs_n >= 1_000:
        return f"{sign}${abs_n / 1_000:.1f}K"
    return f"{sign}${abs_n:,.0f}"


def _fmt_int(v: Optional[int]) -> str:
    if v is None:
        return "--"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "--"


def _fmt_str(v: Any, default: str = "--") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _truncate(s: Optional[str], n: int) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "..."


def _para(text: str, style=_BODY) -> Paragraph:
    """Wrap text in a Paragraph, escaping the bare minimum for ReportLab."""
    if text is None:
        text = ""
    safe = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return Paragraph(safe, style)


def _kv_row(label: str, value: str) -> List[Paragraph]:
    return [_para(label, _LABEL), _para(value)]


def _section_header(text: str) -> Paragraph:
    return _para(text, _H2)


def _no_data() -> Paragraph:
    return _para("No data available.", _NA)


# ----- page builders -----------------------------------------------------

def _build_identity_panel(p: Dict[str, Any]) -> List:
    """Page 1 top: identity + addresses. Returns flowables."""
    flow: List = []
    name = _fmt_str(p.get("display_name") or p.get("canonical_name"))
    flow.append(_para(name, _H1))

    sub_bits = []
    if p.get("naics"):
        sub_bits.append(f"NAICS {p['naics']}")
    if p.get("industry_text"):
        sub_bits.append(_truncate(p["industry_text"], 80))
    if p.get("employee_count"):
        sub_bits.append(f"{_fmt_int(p['employee_count'])} employees")
    if p.get("is_public"):
        sub_bits.append("Public company")
    if p.get("is_federal_contractor"):
        sub_bits.append("Federal contractor")
    if p.get("is_nonprofit"):
        sub_bits.append("Nonprofit")
    if sub_bits:
        flow.append(_para(" · ".join(sub_bits), _BODY_SMALL))
    flow.append(Spacer(1, 4))

    # Addresses + parent table
    rows: List[List[Paragraph]] = []
    addr_parts = [p.get("city"), p.get("state"), p.get("zip")]
    addr_parts = [a for a in addr_parts if a]
    rows.append(_kv_row(
        "Headquarters",
        ", ".join(addr_parts) if addr_parts else "--",
    ))
    if p.get("ein"):
        rows.append(_kv_row("EIN", p["ein"]))
    if p.get("master_id") is not None:
        rows.append(_kv_row("Master ID", str(p["master_id"])))
    if p.get("ultimate_parent_name"):
        parent = p["ultimate_parent_name"]
        if p.get("ultimate_parent_chain_depth"):
            parent += f" (chain depth {p['ultimate_parent_chain_depth']})"
        rows.append(_kv_row("Ultimate parent", parent))
    if p.get("data_quality_score") is not None:
        rows.append(_kv_row(
            "Data quality score",
            f"{int(p['data_quality_score'])}/100 ({p.get('source_count') or 0} sources)",
        ))
    table = Table(rows, colWidths=[1.3 * inch, _USABLE_WIDTH - 1.3 * inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    flow.append(table)
    return flow


def _build_money_section(p: Dict[str, Any]) -> List:
    flow: List = []
    flow.append(_section_header("Financials"))
    rev = p.get("latest_revenue")
    assets = p.get("latest_assets")
    employees = p.get("employee_count")
    rev_year = p.get("financials_fiscal_year")

    fin_table_rows = [["Metric", "Value", "Year / Source"]]
    fin_table_rows.append([
        "Latest revenue",
        _fmt_money(rev, short=False) if rev else "--",
        _fmt_str(rev_year),
    ])
    fin_table_rows.append([
        "Latest assets",
        _fmt_money(assets, short=False) if assets else "--",
        _fmt_str(rev_year),
    ])
    fin_table_rows.append([
        "Employee count",
        _fmt_int(employees),
        _fmt_str(p.get("employee_count_source")),
    ])
    t = Table(
        fin_table_rows,
        colWidths=[1.6 * inch, 2.0 * inch, _USABLE_WIDTH - 3.6 * inch],
    )
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)
    return flow


def _build_owners_section(p: Dict[str, Any]) -> List:
    """24Q-9 institutional owners (top 5)."""
    flow: List = []
    flow.append(_section_header("24Q-9: Top Institutional Owners (SEC 13F)"))
    owners = p.get("institutional_owners") or []
    if not owners:
        flow.append(_no_data())
        return flow

    period = p.get("institutional_owners_period")
    total_value = p.get("institutional_owners_total_value")
    summary_bits = []
    if total_value:
        summary_bits.append(f"Total reported value: {_fmt_money(total_value)}")
    if period:
        summary_bits.append(f"Period: {period}")
    if p.get("institutional_owners_count"):
        summary_bits.append(
            f"{p['institutional_owners_count']} reporting filers"
        )
    if summary_bits:
        flow.append(_para(" · ".join(summary_bits), _BODY_SMALL))
        flow.append(Spacer(1, 2))

    rows = [["Rank", "Filer", "State", "Value", "Shares"]]
    for i, o in enumerate(owners[:5], start=1):
        rows.append([
            str(i),
            _truncate(_fmt_str(o.get("filer_name")), 50),
            _fmt_str(o.get("filer_state"), default=""),
            _fmt_money(o.get("value")),
            _fmt_int(o.get("shares")),
        ])
    t = Table(
        rows,
        colWidths=[
            0.4 * inch,
            3.1 * inch,
            0.5 * inch,
            1.1 * inch,
            _USABLE_WIDTH - 5.1 * inch,
        ],
    )
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)
    return flow


def _build_political_section(p: Dict[str, Any]) -> List:
    """24Q-41 FEC + 24Q-39 LDA totals on one block."""
    flow: List = []
    flow.append(_section_header("24Q-24/39/41: Political Money"))

    # Two side-by-side mini blocks: FEC (left), LDA (right).
    fec = p.get("fec") or {}
    lda = p.get("lobbying") or {}
    fec_total_pac = fec.get("pac_dollars_total") or 0
    fec_total_emp = fec.get("employee_dollars_total") or 0
    fec_combined = fec_total_pac + fec_total_emp

    fec_lines = []
    if fec_combined > 0:
        fec_lines.append(("FEC contributions (combined)", _fmt_money(fec_combined)))
        fec_lines.append(("Corporate PAC", _fmt_money(fec_total_pac)))
        fec_lines.append(("Employee individual donations", _fmt_money(fec_total_emp)))
        fec_lines.append((
            "PAC committees / recipients",
            f"{_fmt_int(fec.get('pac_committees_count'))} / "
            f"{_fmt_int(fec.get('pac_recipients_count'))}",
        ))
    else:
        fec_lines.append(("FEC contributions", "No data available."))

    lda_total = lda.get("total_spend") or 0
    lda_lines = []
    if lda_total > 0:
        lda_lines.append(("LDA lobbying spend", _fmt_money(lda_total)))
        lda_lines.append(("Filings", _fmt_int(lda.get("total_filings"))))
        lda_lines.append((
            "Active quarters / registrants",
            f"{_fmt_int(lda.get('active_quarters'))} / "
            f"{_fmt_int(lda.get('registrants_count'))}",
        ))
        if lda.get("client_name_used"):
            lda_lines.append(("LDA client", _truncate(lda["client_name_used"], 40)))
    else:
        lda_lines.append(("LDA lobbying", "No data available."))

    # Render as a 2-column grid (FEC + LDA) using a parent table.
    def _kv_table(title: str, lines: List[tuple]) -> Table:
        rows = [[_para(title, _LABEL), _para("", _LABEL)]]
        for label, val in lines:
            rows.append([_para(label, _BODY_SMALL), _para(str(val), _BODY_SMALL)])
        t = Table(rows, colWidths=[1.45 * inch, 2.0 * inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 9.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.3, colors.HexColor("#0B2547")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    grid = Table(
        [[_kv_table("FEC (24Q-24/41)", fec_lines),
          _kv_table("LDA Lobbying (24Q-39)", lda_lines)]],
        colWidths=[_USABLE_WIDTH / 2, _USABLE_WIDTH / 2],
    )
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(grid)
    return flow


def _build_demographics_section(p: Dict[str, Any]) -> List:
    flow: List = []
    flow.append(_section_header("Workforce Demographics"))
    demo = p.get("demographics") or {}
    if not demo or not demo.get("has_data"):
        flow.append(_no_data())
        return flow

    rows = [["Metric", "Value"]]
    method = demo.get("method")
    if method:
        rows.append(["Estimation method", _fmt_str(method)])
    if demo.get("total_workforce") is not None:
        rows.append(["Estimated workforce", _fmt_int(demo["total_workforce"])])
    if demo.get("pct_female") is not None:
        rows.append(["Pct female", f"{float(demo['pct_female']):.1f}%"])
    if demo.get("pct_minority") is not None:
        rows.append(["Pct racial/ethnic minority", f"{float(demo['pct_minority']):.1f}%"])
    if demo.get("pct_under_25") is not None:
        rows.append(["Pct under 25", f"{float(demo['pct_under_25']):.1f}%"])
    if demo.get("pct_55_plus") is not None:
        rows.append(["Pct 55+", f"{float(demo['pct_55_plus']):.1f}%"])
    if demo.get("pct_no_hs") is not None:
        rows.append(["Pct without HS diploma", f"{float(demo['pct_no_hs']):.1f}%"])
    if demo.get("pct_bachelors_plus") is not None:
        rows.append(["Pct bachelor's+", f"{float(demo['pct_bachelors_plus']):.1f}%"])
    if demo.get("pct_uninsured") is not None:
        rows.append(["Pct uninsured", f"{float(demo['pct_uninsured']):.1f}%"])
    if demo.get("vintage_year"):
        rows.append(["Source vintage", _fmt_str(demo["vintage_year"])])

    if len(rows) == 1:
        flow.append(_no_data())
        return flow

    occupations = demo.get("top_occupations") or []
    t = Table(rows, colWidths=[2.6 * inch, _USABLE_WIDTH - 2.6 * inch])
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)

    if occupations:
        flow.append(Spacer(1, 4))
        flow.append(_para("Top occupations", _LABEL))
        occ_rows = [["Rank", "Occupation", "Share"]]
        for i, o in enumerate(occupations[:5], start=1):
            share = o.get("pct") or o.get("share_pct")
            occ_rows.append([
                str(i),
                _truncate(_fmt_str(o.get("name") or o.get("occupation_name")), 60),
                f"{float(share):.1f}%" if share is not None else "--",
            ])
        ot = Table(
            occ_rows,
            colWidths=[0.4 * inch, _USABLE_WIDTH - 1.4 * inch, 1.0 * inch],
        )
        ot.setStyle(_TABLE_BASE_STYLE)
        flow.append(ot)
    return flow


def _build_enforcement_section(p: Dict[str, Any]) -> List:
    flow: List = []
    flow.append(_section_header("Enforcement Footprint"))

    osha = p.get("osha") or {}
    nlrb = p.get("nlrb") or {}
    whd = p.get("whd") or {}
    epa = p.get("epa") or {}

    rows = [["Source", "Cases / Records", "Penalties / Backwages", "Worst record"]]

    osha_present = osha.get("inspection_count") or osha.get("violation_count") or osha.get("penalty_total")
    if osha_present:
        worst = osha.get("worst_inspection_label") or osha.get("worst_record") or "--"
        rows.append([
            "OSHA",
            f"{_fmt_int(osha.get('inspection_count'))} insp / "
            f"{_fmt_int(osha.get('violation_count'))} viol",
            _fmt_money(osha.get("penalty_total")),
            _truncate(worst, 50),
        ])
    else:
        rows.append(["OSHA", "No data available.", "--", "--"])

    if nlrb.get("election_count") or nlrb.get("ulp_count"):
        wins = nlrb.get("union_wins")
        losses = nlrb.get("union_losses")
        wl = ""
        if wins is not None or losses is not None:
            wl = f" (W:{_fmt_int(wins)} / L:{_fmt_int(losses)})"
        rows.append([
            "NLRB",
            f"{_fmt_int(nlrb.get('election_count'))} elections{wl} / "
            f"{_fmt_int(nlrb.get('ulp_count'))} ULPs",
            "--",
            _truncate(_fmt_str(nlrb.get("latest_label") or nlrb.get("latest_election")), 50),
        ])
    else:
        rows.append(["NLRB", "No data available.", "--", "--"])

    if whd.get("case_count") or whd.get("backwages_total"):
        rows.append([
            "WHD",
            f"{_fmt_int(whd.get('case_count'))} cases / "
            f"{_fmt_int(whd.get('violation_count'))} viol",
            f"{_fmt_money(whd.get('backwages_total'))} backwages",
            _truncate(_fmt_str(whd.get("worst_record")), 50),
        ])
    else:
        rows.append(["WHD", "No data available.", "--", "--"])

    if epa.get("facility_count"):
        air = "Yes" if epa.get("any_air_flag") else "No"
        rows.append([
            "EPA ECHO",
            f"{_fmt_int(epa.get('facility_count'))} facilities / "
            f"{_fmt_int(epa.get('inspection_count'))} insp",
            _fmt_money(epa.get("penalty_total")),
            f"Air-quality flag: {air} / SNC: {_fmt_int(epa.get('snc_count'))}",
        ])
    else:
        rows.append(["EPA ECHO", "No data available.", "--", "--"])

    t = Table(
        rows,
        colWidths=[0.85 * inch, 2.05 * inch, 1.55 * inch, _USABLE_WIDTH - 4.45 * inch],
    )
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)
    return flow


def _build_directors_section(p: Dict[str, Any]) -> List:
    flow: List = []
    flow.append(_section_header("24Q-10/14: Board of Directors (top 5)"))
    directors = p.get("directors") or []
    if not directors:
        flow.append(_no_data())
        return flow

    rows = [["Director", "Position", "Independent", "Other Boards", "Risk"]]
    for d in directors[:5]:
        risk = d.get("enforcement_risk") or {}
        rows.append([
            _truncate(_fmt_str(d.get("name")), 32),
            _truncate(_fmt_str(d.get("position")), 28),
            "Yes" if d.get("is_independent") else (
                "No" if d.get("is_independent") is False else "--"
            ),
            _fmt_int(risk.get("other_boards_count")),
            f"{risk.get('risk_tier','--')} ({risk.get('risk_score','--')})"
            if risk else "--",
        ])
    t = Table(
        rows,
        colWidths=[
            2.0 * inch, 2.0 * inch, 0.7 * inch, 0.85 * inch,
            _USABLE_WIDTH - 5.55 * inch,
        ],
    )
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)

    flow.append(Spacer(1, 3))
    summary = p.get("director_network_stats") or {}
    if summary:
        line = (
            f"Director network: {_fmt_int(summary.get('one_hop_count'))} 1-hop "
            f"neighbors, {_fmt_int(summary.get('two_hop_count'))} 2-hop "
            f"neighbors, {_fmt_int(summary.get('shared_directors_total'))} "
            "shared directors total."
        )
        flow.append(_para(line, _BODY_SMALL))
    return flow


def _build_executives_section(p: Dict[str, Any]) -> List:
    flow: List = []
    flow.append(_section_header("24Q-7/8: Top Executives"))
    execs = p.get("executives") or []
    if not execs:
        flow.append(_no_data())
        return flow

    rows = [["Rank", "Name", "Title"]]
    for e in execs[:5]:
        rows.append([
            _fmt_str(e.get("title_rank_label"), default=""),
            _truncate(_fmt_str(e.get("name")), 38),
            _truncate(_fmt_str(e.get("title")), 70),
        ])
    t = Table(
        rows,
        colWidths=[1.3 * inch, 2.3 * inch, _USABLE_WIDTH - 3.6 * inch],
    )
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)
    return flow


def _build_tier_section(p: Dict[str, Any]) -> List:
    flow: List = []
    flow.append(_section_header("Targeting Score & Tier"))

    tier = p.get("gold_standard_tier")
    score = p.get("score_value")
    score_kind = p.get("score_kind")  # 'unified' or 'pillar'
    rows = [["Field", "Value"]]
    rows.append(["Gold-standard tier",
                 _fmt_str(tier.title() if isinstance(tier, str) else tier)])
    if score is not None:
        rows.append([
            f"Score ({_fmt_str(score_kind)})",
            f"{float(score):.2f}" if score is not None else "--",
        ])
    if p.get("pillar_anger") is not None:
        rows.append(["Pillar -- Anger", f"{float(p['pillar_anger']):.2f}"])
    if p.get("pillar_leverage") is not None:
        rows.append(["Pillar -- Leverage", f"{float(p['pillar_leverage']):.2f}"])
    if p.get("pillar_stability") is not None:
        rows.append(["Pillar -- Stability", f"{float(p['pillar_stability']):.2f}"])
    if p.get("signals_present") is not None:
        rows.append(["Signals present", _fmt_int(p["signals_present"])])
    if p.get("has_thin_data"):
        rows.append(["Thin data flag", "Yes -- treat tier as advisory."])

    if len(rows) <= 1:
        flow.append(_no_data())
        return flow
    t = Table(rows, colWidths=[2.4 * inch, _USABLE_WIDTH - 2.4 * inch])
    t.setStyle(_TABLE_BASE_STYLE)
    flow.append(t)
    return flow


def _footer(canvas, doc, payload: Dict[str, Any]) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    name = (payload.get("display_name") or payload.get("canonical_name") or "")
    mid = payload.get("master_id")
    generated_at = payload.get("generated_at") or datetime.utcnow().isoformat()
    left = f"Power Profile -- {name} (master_id={mid})"
    right = f"Generated {generated_at}Z   Page {doc.page} of 3"
    canvas.drawString(_LEFT_MARGIN, 0.3 * inch, left[:90])
    canvas.drawRightString(_PAGE_W - _RIGHT_MARGIN, 0.3 * inch, right)
    canvas.restoreState()


# ----- public entry point -----------------------------------------------

def render_power_profile_pdf(payload: Dict[str, Any]) -> bytes:
    """Render the 3-page power profile PDF for an employer.

    Parameters
    ----------
    payload : dict
        Pre-aggregated by the router. See `api/routers/power_profile.py`
        for the canonical key list. Missing keys render as "No data
        available." inside the relevant section -- this function will
        not raise on partial data.

    Returns
    -------
    bytes
        The complete PDF byte stream, ready to stream as the HTTP response.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=_LEFT_MARGIN,
        rightMargin=_RIGHT_MARGIN,
        topMargin=_TOP_MARGIN,
        bottomMargin=_BOTTOM_MARGIN,
        title=f"Power Profile -- {payload.get('display_name') or payload.get('master_id')}",
        author="Labor Data Terminal",
        subject="Employer Power Profile (3-page organizer briefing)",
    )

    flow: List = []

    # --- Page 1: Identity & Money ---
    flow.extend(_build_identity_panel(payload))
    flow.append(Spacer(1, 6))
    flow.extend(_build_money_section(payload))
    flow.append(Spacer(1, 4))
    flow.extend(_build_owners_section(payload))
    flow.append(Spacer(1, 4))
    flow.extend(_build_political_section(payload))
    flow.append(PageBreak())

    # --- Page 2: Workforce & Enforcement ---
    flow.append(_para("Workforce & Enforcement", _H1))
    flow.append(Spacer(1, 4))
    flow.extend(_build_demographics_section(payload))
    flow.append(Spacer(1, 6))
    flow.extend(_build_enforcement_section(payload))
    flow.append(PageBreak())

    # --- Page 3: Network & Risk ---
    flow.append(_para("Network & Risk", _H1))
    flow.append(Spacer(1, 4))
    flow.extend(_build_directors_section(payload))
    flow.append(Spacer(1, 6))
    flow.extend(_build_executives_section(payload))
    flow.append(Spacer(1, 6))
    flow.extend(_build_tier_section(payload))

    def _on_page(c, d):
        _footer(c, d, payload)

    doc.build(flow, onFirstPage=_on_page, onLaterPages=_on_page)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
