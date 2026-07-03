"""Report generation services."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import BytesIO
from io import StringIO

from sqlalchemy import text

from models import db


def defect_distribution_rows(start: datetime, end: datetime):
    """Return (defect, count) rows using normalized rows plus legacy fallback."""
    dialect = db.session.get_bind().dialect.name
    params = {"start": start, "end": end}

    normalized_sql = text("""
        SELECT defect_types.name AS defect, count(*) AS defect_count
        FROM inspection_defects
        JOIN defect_types ON defect_types.id = inspection_defects.defect_type_id
        JOIN inspections ON inspections.id = inspection_defects.inspection_id
        WHERE inspections.timestamp >= :start
          AND inspections.timestamp < :end
        GROUP BY defect_types.name
    """)

    if dialect == "sqlite":
        legacy_sql = text("""
            WITH RECURSIVE defect_parts(defect, rest) AS (
                SELECT '', defects || ','
                FROM inspections
                WHERE timestamp >= :start
                  AND timestamp < :end
                  AND defects IS NOT NULL
                  AND defects != ''
                  AND NOT EXISTS (
                      SELECT 1
                      FROM inspection_defects
                      WHERE inspection_defects.inspection_id = inspections.id
                  )
                UNION ALL
                SELECT
                    trim(substr(rest, 0, instr(rest, ','))),
                    substr(rest, instr(rest, ',') + 1)
                FROM defect_parts
                WHERE rest != ''
            )
            SELECT defect, count(*) AS defect_count
            FROM defect_parts
            WHERE defect != ''
            GROUP BY defect
        """)
    elif dialect == "postgresql":
        legacy_sql = text("""
            SELECT defect, count(*) AS defect_count
            FROM (
                SELECT trim(defect_parts.part) AS defect
                FROM inspections
                CROSS JOIN LATERAL unnest(string_to_array(inspections.defects, ',')) AS defect_parts(part)
                WHERE timestamp >= :start
                  AND timestamp < :end
                  AND defects IS NOT NULL
                  AND defects != ''
                  AND NOT EXISTS (
                      SELECT 1
                      FROM inspection_defects
                      WHERE inspection_defects.inspection_id = inspections.id
                  )
            ) AS defect_parts
            WHERE defect != ''
            GROUP BY defect
        """)
    else:
        raise RuntimeError(f"Unsupported report aggregation dialect: {dialect}")

    counts: dict[str, int] = {}
    for sql in (normalized_sql, legacy_sql):
        for row in db.session.execute(sql, params):
            counts[row.defect] = counts.get(row.defect, 0) + int(row.defect_count)

    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def build_inspection_report_pdf(
    inspections,
    *,
    start: datetime,
    end: datetime,
    total_matches: int,
    max_rows: int,
) -> BytesIO:
    """Build an inspection PDF report and return a rewound byte buffer."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=6,
        textColor=colors.HexColor("#006400"),
    )
    elements.append(Paragraph("NHA — Inspection Report", title_style))

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#555555"),
        spaceAfter=16,
    )
    elements.append(
        Paragraph(
            f"Period: {start.strftime('%B %d, %Y')} — {(end - timedelta(days=1)).strftime('%B %d, %Y')}  |  "
            f"Included: {len(inspections)} of {total_matches} inspections  |  Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y %I:%M %p')}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 8))

    if total_matches > len(inspections):
        elements.append(
            Paragraph(
                f"Report truncated to the latest {max_rows} inspections. Narrow the date range for a complete export.",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 8))

    if inspections:
        table_data = [["ID", "Date & Time", "Plate", "Location", "Camera", "Status", "Confidence", "Defects"]]
        cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=10)
        for insp in inspections:
            table_data.append([
                str(insp.id),
                insp.timestamp.strftime("%b %d, %Y %I:%M %p"),
                insp.plate or "—",
                Paragraph(insp.location[:35], cell_style),
                insp.camera or "—",
                insp.status.upper(),
                f"{insp.confidence}%",
                Paragraph(", ".join(insp.defect_list) or "None", cell_style),
            ])

        col_widths = [0.4 * inch, 1.3 * inch, 0.8 * inch, 2.2 * inch, 0.7 * inch, 0.6 * inch, 0.8 * inch, 2.0 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#006400")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f7f0")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (5, 0), (6, -1), "CENTER"),
        ]))

        for row_index, insp in enumerate(inspections, start=1):
            if insp.status == "unsafe":
                table.setStyle(TableStyle([
                    ("TEXTCOLOR", (5, row_index), (5, row_index), colors.HexColor("#dc2626")),
                    ("FONTNAME", (5, row_index), (5, row_index), "Helvetica-Bold"),
                ]))
            else:
                table.setStyle(TableStyle([
                    ("TEXTCOLOR", (5, row_index), (5, row_index), colors.HexColor("#16a34a")),
                ]))

        elements.append(table)
    else:
        elements.append(Paragraph("No inspections found in the selected date range.", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def build_inspection_report_csv(inspections) -> BytesIO:
    """Build a CSV inspection export and return a rewound byte buffer."""
    text_buffer = StringIO()
    writer = csv.writer(text_buffer)
    writer.writerow([
        "id",
        "timestamp",
        "plate",
        "location",
        "camera",
        "status",
        "confidence",
        "defects",
        "review_status",
        "correction_label",
        "model_class",
        "model_version",
        "model_threshold",
        "inference_ms",
        "created_by",
    ])
    for insp in inspections:
        writer.writerow([
            insp.id,
            insp.timestamp.isoformat() if insp.timestamp else "",
            insp.plate or "",
            insp.location or "",
            insp.camera or "",
            insp.status,
            insp.confidence,
            "; ".join(insp.defect_list),
            insp.review_status,
            insp.correction_label or "",
            insp.predicted_class or "",
            insp.model_version or "",
            insp.model_threshold if insp.model_threshold is not None else "",
            insp.inference_ms if insp.inference_ms is not None else "",
            insp.created_by.email if insp.created_by else "",
        ])

    buffer = BytesIO(text_buffer.getvalue().encode("utf-8-sig"))
    buffer.seek(0)
    return buffer
