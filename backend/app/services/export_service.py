"""
Export Service
Generates CSV and PDF compatibility reports from call data.

PDF format is designed to be a printable vendor sign-off report:
- cover page with summary stats and pass/fail verdict
- call-by-call detail table
- one page per capture file if filtered, or all-calls summary otherwise
"""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.call import Call, CallStatus
from app.models.capture_file import CaptureFile
from app.models.rtp_stream import RTPStream


# ── Status display helpers ────────────────────────────────────────────────

STATUS_LABELS = {
    "ANSWERED":  "Answered",
    "MISSED":    "Missed",
    "REJECTED":  "Rejected",
    "FAILED":    "Failed",
    "CANCELLED": "Cancelled",
    "UNKNOWN":   "Unknown",
}

STATUS_COLORS_RGB = {
    "ANSWERED":  (0.18, 0.49, 0.20),   # green
    "MISSED":    (0.80, 0.55, 0.00),   # amber
    "REJECTED":  (0.78, 0.11, 0.11),   # red
    "FAILED":    (0.40, 0.40, 0.40),   # grey
    "CANCELLED": (0.08, 0.46, 0.74),   # blue
    "UNKNOWN":   (0.38, 0.44, 0.46),   # slate
}


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def _fetch_calls(
    db: AsyncSession,
    capture_file_id: Optional[int] = None,
) -> tuple[list[Call], Optional[CaptureFile], dict[int, list[RTPStream]]]:
    """Fetch calls, the capture file metadata, and RTP streams keyed by call.id."""
    q = select(Call).order_by(Call.start_time)
    if capture_file_id is not None:
        q = q.where(Call.capture_file_id == capture_file_id)
    result = await db.execute(q)
    calls = result.scalars().all()

    cf: Optional[CaptureFile] = None
    if capture_file_id is not None:
        r2 = await db.execute(select(CaptureFile).where(CaptureFile.id == capture_file_id))
        cf = r2.scalar_one_or_none()

    # Fetch all RTP streams for these calls in one query
    call_ids = [c.id for c in calls]
    rtp_map: dict[int, list[RTPStream]] = {}
    if call_ids:
        r3 = await db.execute(select(RTPStream).where(RTPStream.call_id.in_(call_ids)))
        for stream in r3.scalars().all():
            rtp_map.setdefault(stream.call_id, []).append(stream)

    return list(calls), cf, rtp_map


# ── CSV export ────────────────────────────────────────────────────────────

async def generate_csv(
    db: AsyncSession,
    capture_file_id: Optional[int] = None,
) -> bytes:
    """
    Generate a CSV byte string of all calls (optionally filtered by capture file).
    Columns match the dashboard call table plus extra fields useful for analysis.
    """
    calls, _, _ = await _fetch_calls(db, capture_file_id)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Call-ID",
        "Caller",
        "Called",
        "Display Name",
        "Status",
        "SIP Code",
        "Rejection Reason",
        "Start Time",
        "Ring Duration (s)",
        "Talk Duration (s)",
        "Total Duration (s)",
        "Source IP",
        "Destination IP",
        "User Agent",
        "SIP Domain",
    ])

    for c in calls:
        writer.writerow([
            c.call_id,
            c.caller or "",
            c.called or "",
            c.display_name or "",
            c.status.value if c.status else "",
            c.sip_result_code or "",
            c.rejection_reason or "",
            _fmt_dt(c.start_time),
            round(c.ring_duration, 2) if c.ring_duration is not None else "",
            round(c.talk_duration, 2) if c.talk_duration is not None else "",
            round(c.total_duration, 2) if c.total_duration is not None else "",
            c.source_ip or "",
            c.destination_ip or "",
            c.user_agent or "",
            c.sip_domain or "",
        ])

    return output.getvalue().encode("utf-8")


# ── PDF export ────────────────────────────────────────────────────────────

async def generate_pdf(
    db: AsyncSession,
    capture_file_id: Optional[int] = None,
    vendor_name: str = "",
) -> bytes:
    """
    Generate a PDF compatibility report as bytes.
    Designed to be printed and handed to a PBX vendor as evidence of
    call compatibility testing.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    calls, cf, rtp_map = await _fetch_calls(db, capture_file_id)

    # ── Count statuses ────────────────────────────────────────────────────
    counts: dict[str, int] = {}
    for c in calls:
        key = c.status.value if c.status else "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1

    total = len(calls)
    answered = counts.get("ANSWERED", 0)

    # ── Document setup ────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="SIP Compatibility Report",
        author="VoIP SIP Analyzer",
    )
    W = A4[0] - 40 * mm  # usable width

    # ── Styles ────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=base["Title"],
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#0d1117"),
        alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=base["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#57606a"),
        alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=base["Heading2"],
        fontSize=12,
        leading=16,
        spaceBefore=12,
        textColor=colors.HexColor("#0d1117"),
    )
    label_style = ParagraphStyle(
        "Label",
        parent=base["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#57606a"),
        spaceAfter=1,
    )
    value_style = ParagraphStyle(
        "Value",
        parent=base["Normal"],
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0d1117"),
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=base["Normal"],
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#24292f"),
    )
    # Separate style for table header cells — white text so it's readable
    # against the dark (#0d1117) header row background.
    header_cell_style = ParagraphStyle(
        "HeaderCell",
        parent=base["Normal"],
        fontSize=7.5,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )
    mono_style = ParagraphStyle(
        "Mono",
        parent=base["Normal"],
        fontName="Courier",
        fontSize=6.5,
        leading=9,
        textColor=colors.HexColor("#57606a"),
    )

    # ── Build story ───────────────────────────────────────────────────────
    story = []

    # Header bar (dark background simulation via coloured Table)
    header_data = [[
        Paragraph("<b><font color='#ffffff' size='14'>VoIP SIP Analyzer</font></b>", base["Normal"]),
        Paragraph(
            f"<font color='#8b949e' size='8'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</font>",
            ParagraphStyle("HR", parent=base["Normal"], alignment=TA_RIGHT),
        ),
    ]]
    header_table = Table(header_data, colWidths=[W * 0.6, W * 0.4])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0d1117")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (0, -1), 12),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10 * mm))

    # Title block
    story.append(Paragraph("SIP Compatibility Report", title_style))
    story.append(Spacer(1, 2 * mm))

    subtitle_parts = []
    if vendor_name:
        subtitle_parts.append(f"Vendor: {vendor_name}")
    if cf:
        subtitle_parts.append(f"Capture file: {cf.filename}")
    else:
        subtitle_parts.append("All capture files")
    story.append(Paragraph("  ·  ".join(subtitle_parts), subtitle_style))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor("#d0d7de")))
    story.append(Spacer(1, 6 * mm))

    # ── KPI row ───────────────────────────────────────────────────────────
    kpi_rows = [[
        _kpi_cell("Total Calls",  str(total),                          "#0d1117", base),
        _kpi_cell("Answered",     str(answered),                       "#1a7f37", base),
        _kpi_cell("Missed",       str(counts.get("MISSED", 0)),        "#9a6700", base),
        _kpi_cell("Rejected",     str(counts.get("REJECTED", 0)),      "#cf222e", base),
        _kpi_cell("Failed",       str(counts.get("FAILED", 0)),        "#57606a", base),
        _kpi_cell("Cancelled",    str(counts.get("CANCELLED", 0)),     "#0969da", base),
    ]]
    kpi_table = Table(kpi_rows, colWidths=[W / 6] * 6)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f8fa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 8 * mm))

    # ── Status breakdown bar (visual) ─────────────────────────────────────
    if total > 0:
        story.append(Paragraph("Status Breakdown", section_style))
        story.append(Spacer(1, 2 * mm))

        bar_data = []
        for status, label in STATUS_LABELS.items():
            count = counts.get(status, 0)
            if count == 0:
                continue
            pct = count / total * 100
            bar_data.append([
                Paragraph(label, cell_style),
                Paragraph(str(count), cell_style),
                Paragraph(f"{pct:.1f}%", cell_style),
            ])

        if bar_data:
            bar_table = Table(bar_data, colWidths=[40 * mm, 20 * mm, W - 60 * mm])
            bar_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ]))
            story.append(bar_table)
        story.append(Spacer(1, 6 * mm))

    # ── Call detail table ─────────────────────────────────────────────────
    story.append(Paragraph("Call Detail", section_style))
    story.append(Spacer(1, 2 * mm))

    col_w = [W * p for p in [0.26, 0.09, 0.09, 0.11, 0.07, 0.07, 0.16, 0.15]]
    table_data = [[
        Paragraph("Call-ID",     header_cell_style),
        Paragraph("Caller",      header_cell_style),
        Paragraph("Called",      header_cell_style),
        Paragraph("Start Time",  header_cell_style),
        Paragraph("Ring",        header_cell_style),
        Paragraph("Talk",        header_cell_style),
        Paragraph("Status",      header_cell_style),
        Paragraph("Media",       header_cell_style),
    ]]

    for c in calls:
        status_str = c.status.value if c.status else "UNKNOWN"
        rgb = STATUS_COLORS_RGB.get(status_str, (0.4, 0.4, 0.4))
        hex_col = "#{:02x}{:02x}{:02x}".format(
            int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
        )
        call_id_display = c.call_id if len(c.call_id) <= 36 else c.call_id[:16] + "..." + c.call_id[-12:]
        status_label = STATUS_LABELS.get(status_str, status_str)
        if c.rejection_reason:
            status_label += f"\n{c.sip_result_code} {c.rejection_reason}"

        # Build media summary for this call
        streams = rtp_map.get(c.id, [])
        if streams:
            one_way = any(s.is_one_way for s in streams)
            avg_jitter = sum(s.jitter_ms or 0 for s in streams) / len(streams)
            avg_loss   = sum(s.packet_loss_pct or 0 for s in streams) / len(streams)
            codec      = streams[0].codec or "—"
            if one_way:
                media_text = f'<font color="#cf222e">⚠ One-way\n{codec}</font>'
            elif avg_loss > 5 or avg_jitter > 50:
                media_text = f'<font color="#e36209">Poor\n{codec} J:{avg_jitter:.0f}ms L:{avg_loss:.0f}%</font>'
            elif avg_loss > 1 or avg_jitter > 20:
                media_text = f'<font color="#9a6700">Fair\n{codec} J:{avg_jitter:.0f}ms</font>'
            else:
                media_text = f'<font color="#1a7f37">Good\n{codec}</font>'
        else:
            media_text = '<font color="#8b949e">—</font>'

        table_data.append([
            Paragraph(f'<font name="Courier" size="6">{call_id_display}</font>', cell_style),
            Paragraph(c.caller or "—", cell_style),
            Paragraph(c.called or "—", cell_style),
            Paragraph(_fmt_dt(c.start_time), cell_style),
            Paragraph(_fmt_duration(c.ring_duration), cell_style),
            Paragraph(_fmt_duration(c.talk_duration), cell_style),
            Paragraph(f'<b><font color="{hex_col}">{status_label}</font></b>', cell_style),
            Paragraph(media_text, cell_style),
        ])

    call_table = Table(table_data, colWidths=col_w, repeatRows=1)
    call_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d1117")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        # Data rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d7de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(call_table)

    # ── Media Quality Summary ─────────────────────────────────────────────
    # Collect all RTP streams for calls in this report
    all_streams = []
    one_way_calls = []
    for c in calls:
        streams = rtp_map.get(c.id, [])
        all_streams.extend(streams)
        if any(s.is_one_way for s in streams):
            one_way_calls.append(c.caller or c.call_id[:20])

    if all_streams:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Media Quality Summary", section_style))
        story.append(Spacer(1, 3 * mm))

        # Aggregate metrics across all streams
        avg_jitter  = sum(s.jitter_ms or 0 for s in all_streams) / len(all_streams)
        max_jitter  = max(s.jitter_max_ms or 0 for s in all_streams)
        avg_loss    = sum(s.packet_loss_pct or 0 for s in all_streams) / len(all_streams)
        total_pkts  = sum(s.packet_count or 0 for s in all_streams)
        lost_pkts   = sum(s.packet_loss_count or 0 for s in all_streams)
        codecs      = sorted({s.codec for s in all_streams if s.codec})
        n_one_way   = len(one_way_calls)

        # Quality rating
        if avg_loss > 5 or avg_jitter > 50 or n_one_way > 0:
            qual_txt, qual_color = "Poor", "#cf222e"
        elif avg_loss > 1 or avg_jitter > 20:
            qual_txt, qual_color = "Fair", "#9a6700"
        else:
            qual_txt, qual_color = "Good", "#1a7f37"

        media_kpi_rows = [[
            _kpi_cell("Streams",       str(len(all_streams)),           "#0d1117", base),
            _kpi_cell("Avg Jitter",    f"{avg_jitter:.1f} ms",          "#0969da", base),
            _kpi_cell("Max Jitter",    f"{max_jitter:.1f} ms",          "#0969da", base),
            _kpi_cell("Avg Loss",      f"{avg_loss:.1f}%",              "#cf222e" if avg_loss > 1 else "#1a7f37", base),
            _kpi_cell("Total Packets", str(total_pkts),                 "#57606a", base),
            _kpi_cell("Quality",       qual_txt,                        qual_color, base),
        ]]
        media_kpi = Table(media_kpi_rows, colWidths=[W / 6] * 6)
        media_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f8fa")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(media_kpi)

        # Codec and one-way audio notes
        if codecs or one_way_calls:
            story.append(Spacer(1, 4 * mm))
            notes = []
            if codecs:
                notes.append(f"Codecs detected: {', '.join(codecs)}")
            if one_way_calls:
                notes.append(
                    f"⚠ One-way audio detected on {n_one_way} call(s): "
                    + ", ".join(one_way_calls[:5])
                    + (" …" if len(one_way_calls) > 5 else "")
                )
            warn_style = ParagraphStyle(
                "MediaNote", parent=base["Normal"], fontSize=8,
                textColor=colors.HexColor("#57606a"), spaceAfter=3,
            )
            for note in notes:
                color = "#cf222e" if "⚠" in note else "#57606a"
                story.append(Paragraph(
                    f'<font color="{color}">{note}</font>', warn_style
                ))

    # ── Footer note ───────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor("#d0d7de")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Generated by VoIP SIP Analyzer &mdash; https://github.com/eksalih/VoIP_SIP_Analyzer",
        ParagraphStyle("Footer", parent=base["Normal"], fontSize=7,
                       textColor=colors.HexColor("#57606a"), alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()


def _kpi_cell(label: str, value: str, value_color: str, base) -> list:
    """Helper: builds a [label, value] paragraph pair for the KPI row."""
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    lbl = ParagraphStyle("kl", parent=base["Normal"], fontSize=7,
                         textColor=colors.HexColor("#57606a"), alignment=TA_CENTER)
    val = ParagraphStyle("kv", parent=base["Normal"], fontSize=16, fontName="Helvetica-Bold",
                         textColor=colors.HexColor(value_color), alignment=TA_CENTER)
    return [
        Paragraph(label, lbl),
        Paragraph(value, val),
    ]
