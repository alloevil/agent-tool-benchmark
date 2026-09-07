#!/usr/bin/env python3
"""Generate the five PDF fixtures + expected-element JSON files.

Single source of truth: every string that the scorer later looks for is a
Python literal in this file, used BOTH to lay out the PDF and to write the
expected/*.json ground truth. Run with the repo venv:

    ../../.venv/bin/python generate_pdfs.py

PDFs are byte-reproducible: reportlab's `invariant` canvas mode pins the
CreationDate and document ID.
"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected"
EXPECTED.mkdir(exist_ok=True)

# Built-in CID font: no font file embedding, deterministic, and text
# extraction works through the standard Adobe-GB1 CMap.
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


class InvariantCanvas(canvas.Canvas):
    """Canvas with invariant=1 -> fixed CreationDate/ID, reproducible bytes."""

    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("Body", parent=STYLES["Normal"], fontSize=10.5, leading=14,
                      alignment=TA_JUSTIFY, spaceAfter=6)
H1 = ParagraphStyle("H1x", parent=STYLES["Heading1"], fontSize=18, spaceAfter=10)
H2 = ParagraphStyle("H2x", parent=STYLES["Heading2"], fontSize=14, spaceAfter=8)
H3 = ParagraphStyle("H3x", parent=STYLES["Heading3"], fontSize=12, spaceAfter=6)
CODE = ParagraphStyle("Codex", parent=STYLES["Code"], fontSize=9, leading=11,
                      leftIndent=12, spaceBefore=6, spaceAfter=6)
CJK_BODY = ParagraphStyle("CjkBody", parent=BODY, fontName="STSong-Light",
                          fontSize=10.5, leading=16)
CJK_H1 = ParagraphStyle("CjkH1", parent=H1, fontName="STSong-Light")
CJK_H2 = ParagraphStyle("CjkH2", parent=H2, fontName="STSong-Light")


def build(path: Path, flowables):
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.2 * cm, bottomMargin=2.2 * cm,
        title=path.stem, author="fixture-generator",
    )
    doc.build(flowables, canvasmaker=InvariantCanvas)


def write_expected(name: str, data: dict):
    data = {"name": name, **data}
    (EXPECTED / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 01 simple
def fixture_simple():
    h1 = "The Voyager Interstellar Mission"
    h2a = "Mission Overview"
    h2b = "Scientific Instruments"
    h3 = "The Low-Energy Charged Particle Detector"
    s1 = ("Both spacecraft were launched in 1977 to exploit a rare planetary "
          "alignment that occurs once every 176 years.")
    s2 = ("Voyager 1 crossed the heliopause in August 2012, becoming the "
          "first human-made object to enter interstellar space.")
    s3 = ("The detector measures ions with energies between 22 keV and "
          "several hundred MeV using two solid-state telescope heads.")
    bold_phrase = "grand tour trajectory"

    flow = [
        Paragraph(h1, H1),
        Paragraph(h2a, H2),
        Paragraph(
            f"{s1} Engineers called this opportunity the <b>{bold_phrase}</b>, "
            "because a single gravity-assist chain could reach all four outer "
            "planets in under twelve years.", BODY),
        Paragraph(s2 + " Its twin followed six years later at a different "
                       "heliographic latitude.", BODY),
        Paragraph(h2b, H2),
        Paragraph("Each spacecraft carries eleven investigations, most of "
                  "which still return data on a 22.4-watt downlink.", BODY),
        Paragraph(h3, H3),
        Paragraph(s3, BODY),
    ]
    build(HERE / "01-simple.pdf", flow)
    write_expected("01-simple", {
        "headings": [h1, h2a, h2b, h3],
        "key_sentences": [s1, s2, s3, bold_phrase],
    })


# ----------------------------------------------------------------- 02 table
TABLE_HEADER = ["Probe", "Launched", "Primary target", "Status 2026"]
TABLE_ROWS = [
    ["Voyager 1", "1977-09-05", "Jupiter flyby", "interstellar"],
    ["Voyager 2", "1977-08-20", "Neptune flyby", "interstellar"],
    ["Galileo", "1989-10-18", "Jupiter orbit", "deorbited 2003"],
    ["Cassini", "1997-10-15", "Saturn orbit", "deorbited 2017"],
    ["New Horizons", "2006-01-19", "Pluto flyby", "Kuiper belt"],
]


def fixture_table():
    h1 = "Outer Planet Probe Comparison"
    intro = ("The table below lists five outer-planet missions with their "
             "launch dates and current operational status.")
    data = [TABLE_HEADER] + TABLE_ROWS
    tbl = Table(data, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow = [Paragraph(h1, H1), Paragraph(intro, BODY), Spacer(1, 8), tbl]
    build(HERE / "02-table.pdf", flow)
    write_expected("02-table", {
        "headings": [h1],
        "key_sentences": [intro],
        "cells": TABLE_HEADER + [c for row in TABLE_ROWS for c in row],
    })


# ------------------------------------------------------------ 03 two-column
# Column 1 holds sentences A1..A4, column 2 holds B1..B4. Correct reading
# order = all of column 1 before all of column 2. A layout-order extractor
# (naive top-to-bottom across the whole page width) interleaves them.
A_SENT = [
    "Alpine glaciers store roughly seventy percent of the region's freshwater reserve.",
    "Between 2000 and 2020 the average glacier front retreated by nearly one kilometre.",
    "Meltwater timing shifts are already measurable in the Rhone and Po basins.",
    "Downstream hydropower operators have re-licensed reservoirs to buffer the change.",
]
B_SENT = [
    "Model ensembles project that half of today's glacier volume disappears by 2060.",
    "The remaining ice concentrates above four thousand metres of elevation.",
    "Summer river discharge could drop by a quarter in dry years after mid-century.",
    "Adaptation plans therefore prioritise storage, not just emission scenarios.",
]


def fixture_two_column():
    h1 = "Glacier Retreat in the Alps"
    page_w, page_h = A4
    margin = 2.0 * cm
    gutter = 0.8 * cm
    col_w = (page_w - 2 * margin - gutter) / 2
    col_h = page_h - 2 * margin - 1.6 * cm  # leave room for the title band

    doc = BaseDocTemplate(
        str(HERE / "03-two-column.pdf"), pagesize=A4,
        title="03-two-column", author="fixture-generator",
    )
    frame_title = Frame(margin, page_h - margin - 1.4 * cm,
                        page_w - 2 * margin, 1.4 * cm, id="title")
    frame_l = Frame(margin, margin, col_w, col_h, id="left")
    frame_r = Frame(margin + col_w + gutter, margin, col_w, col_h, id="right")
    doc.addPageTemplates([PageTemplate(id="two", frames=[frame_title, frame_l, frame_r])])

    col_style = ParagraphStyle("Col", parent=BODY, fontSize=10, leading=13.5)
    from reportlab.platypus import FrameBreak
    flow = [Paragraph(h1, H1), FrameBreak()]
    for s in A_SENT:
        flow.append(Paragraph(s + " " + FILLER, col_style))
    flow.append(FrameBreak())
    for s in B_SENT:
        flow.append(Paragraph(s + " " + FILLER, col_style))
    doc.build(flow, canvasmaker=InvariantCanvas)

    # Order pairs: (a) consecutive pairs within each column, (b) EVERY
    # (A_i, B_j) cross pair — all left-column text must precede all
    # right-column text. Consecutive pairs alone under-detect paragraph-wise
    # interleaving (A1 B1 A2 B2 ...), which preserves within-column order.
    pairs = []
    for col in (A_SENT, B_SENT):
        pairs.extend([a, b] for a, b in zip(col, col[1:]))
    pairs.extend([a, b] for a in A_SENT for b in B_SENT)
    write_expected("03-two-column", {
        "headings": [h1],
        "key_sentences": A_SENT + B_SENT,
        "order_pairs": pairs,
    })


# Filler keeps each column visually full so layout-order extraction has to
# make a real decision; it is not scored.
FILLER = ("Field surveys, satellite altimetry, and long-running mass-balance "
          "series all agree on the direction of the trend, differing only in "
          "the pace attributed to individual valleys.")


# -------------------------------------------------------- 04 code and lists
CODE_LINES = [
    "def moving_average(xs, k):",
    "    if k <= 0:",
    "        raise ValueError(\"window must be positive\")",
    "    acc = 0.0",
    "    out = []",
    "    for i, x in enumerate(xs):",
    "        acc += x",
    "        if i >= k:",
    "            acc -= xs[i - k]",
    "        out.append(acc / min(i + 1, k))",
    "    return out",
]
LIST_ITEMS_L1 = ["Data ingestion", "Feature preparation", "Model training"]
LIST_ITEMS_L2 = ["schema validation", "null-rate audit", "window normalisation"]


def fixture_code_and_list():
    h1 = "Pipeline Reference"
    h2 = "Smoothing Utility"
    intro = ("The pipeline runs three top-level stages, each with its own "
             "checklist of sub-tasks that must pass before promotion.")
    bullet = ParagraphStyle("Bul", parent=BODY, leftIndent=16, bulletIndent=6)
    bullet2 = ParagraphStyle("Bul2", parent=BODY, leftIndent=34, bulletIndent=24)

    flow = [Paragraph(h1, H1), Paragraph(intro, BODY)]
    for i, item in enumerate(LIST_ITEMS_L1):
        flow.append(Paragraph(item, bullet, bulletText="\u2022"))
        if i == 0:
            for sub in LIST_ITEMS_L2:
                flow.append(Paragraph(sub, bullet2, bulletText="\u25e6"))
    flow.append(Paragraph(h2, H2))
    flow.append(Paragraph("The reference implementation is nine lines of "
                          "dependency-free Python:", BODY))
    flow.append(Preformatted("\n".join(CODE_LINES), CODE))
    build(HERE / "04-code-and-list.pdf", flow)
    write_expected("04-code-and-list", {
        "headings": [h1, h2],
        "key_sentences": [intro] + LIST_ITEMS_L1 + LIST_ITEMS_L2,
        "code_lines": CODE_LINES,
    })


# ------------------------------------------------------------------ 05 cjk
CJK_H1_TEXT = "都江堰水利工程"
CJK_H2_TEXT = "无坝引水的设计原理"
CJK_S1 = "都江堰始建于公元前二五六年,由蜀郡太守李冰父子主持修建。"
CJK_S2 = "鱼嘴分水堤将岷江分为内江和外江,枯水期六成江水进入内江灌溉成都平原。"
CJK_S3 = "宝瓶口宽度约二十米,起到节制闸的作用,防止过量洪水涌入灌区。"
CJK_MIXED = ("联合国教科文组织(UNESCO)于2000年将都江堰列入世界遗产名录,"
             "评价其为 irrigation engineering 的杰出范例。")


def fixture_cjk():
    flow = [
        Paragraph(CJK_H1_TEXT, CJK_H1),
        Paragraph(CJK_S1, CJK_BODY),
        Paragraph(CJK_H2_TEXT, CJK_H2),
        Paragraph(CJK_S2, CJK_BODY),
        Paragraph(CJK_S3, CJK_BODY),
        Paragraph(CJK_MIXED, CJK_BODY),
    ]
    build(HERE / "05-cjk.pdf", flow)
    write_expected("05-cjk", {
        "headings": [CJK_H1_TEXT, CJK_H2_TEXT],
        "cjk_sentences": [CJK_S1, CJK_S2, CJK_S3],
        "key_sentences": ["irrigation engineering", "UNESCO"],
    })


if __name__ == "__main__":
    fixture_simple()
    fixture_table()
    fixture_two_column()
    fixture_code_and_list()
    fixture_cjk()
    for p in sorted(HERE.glob("*.pdf")):
        print(f"{p.name}  {p.stat().st_size} bytes")
