"""
Offer Letter PDF Generation using ReportLab.
Generates professional offer letters matching the Flit frontend design.
"""
import logging
from io import BytesIO
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_offer_letter_pdf(offer_data):
    """
    Generate a professional offer letter PDF matching the Flit platform design.

    Args:
        offer_data (dict): Dictionary containing:
            - candidate_name (str)
            - position_title (str)
            - company_name (str)
            - company_location (str)
            - employer_name (str)
            - employer_position (str)
            - offer_salary (int)
            - salary_currency (str)
            - start_date (str or date)
            - employment_type (str)
            - location (str)
            - offer_terms (str, optional)
            - offer_date (str or date, optional)
            - is_hourly (bool, optional)
            - employer_email (str, optional)

    Returns:
        bytes: PDF file content as bytes.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        from reportlab.lib.colors import HexColor, white
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable
        )
    except ImportError:
        logger.error("ReportLab is not installed. Cannot generate PDF.")
        raise

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Color Palette (matching frontend teal/green design) ──
    teal_dark = HexColor('#1a3c40')
    teal_accent = HexColor('#2d6a6a')
    teal_light = HexColor('#3d8b8b')
    border_gray = HexColor('#e0e0e0')
    bg_light = HexColor('#f8fafa')
    text_dark = HexColor('#1a1a2e')
    text_gray = HexColor('#6b7280')
    text_muted = HexColor('#9ca3af')
    quote_border = HexColor('#d4a843')
    quote_bg = HexColor('#fefce8')
    footer_teal = HexColor('#5fa8a8')

    # ── Custom Styles ────────────────────────────────────────
    style_body = ParagraphStyle(
        'OfferBody', parent=styles['Normal'],
        fontSize=11, textColor=text_dark,
        spaceAfter=8, alignment=TA_JUSTIFY, leading=17,
    )

    style_section_heading = ParagraphStyle(
        'SectionHeading', parent=styles['Normal'],
        fontSize=13, textColor=teal_dark,
        fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=8,
    )

    style_label = ParagraphStyle(
        'DetailLabel', parent=styles['Normal'],
        fontSize=10.5, textColor=teal_accent,
        fontName='Helvetica',
    )

    style_value = ParagraphStyle(
        'DetailValue', parent=styles['Normal'],
        fontSize=11, textColor=text_dark,
        fontName='Helvetica-Bold',
    )

    style_quote = ParagraphStyle(
        'QuoteText', parent=styles['Normal'],
        fontSize=11, textColor=text_dark,
        fontName='Helvetica-Oblique', leading=16,
        leftIndent=12,
    )

    style_footer = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=9, textColor=footer_teal,
        alignment=TA_CENTER,
    )

    style_sig_name = ParagraphStyle(
        'SigName', parent=styles['Normal'],
        fontSize=11.5, textColor=text_dark,
        fontName='Helvetica-Bold', spaceAfter=2,
    )

    style_sig_detail = ParagraphStyle(
        'SigDetail', parent=styles['Normal'],
        fontSize=10, textColor=text_gray,
        spaceAfter=1,
    )

    # ── Extract Data ─────────────────────────────────────────
    candidate_name = offer_data.get('candidate_name', 'Candidate')
    position_title = offer_data.get('position_title', 'Position')
    company_name = offer_data.get('company_name', 'Company')
    employer_name = offer_data.get('employer_name', 'Hiring Manager')
    employer_email = offer_data.get('employer_email', '')
    offer_salary = offer_data.get('offer_salary', 0)
    salary_currency = offer_data.get('salary_currency', 'USD')
    start_date = offer_data.get('start_date', '')
    offer_terms = offer_data.get('offer_terms', '')
    is_hourly = offer_data.get('is_hourly', False)
    offer_date = offer_data.get('offer_date', datetime.now().strftime('%B %d, %Y'))

    # Format dates
    if hasattr(start_date, 'strftime'):
        start_date = start_date.strftime('%B %d, %Y')
    if hasattr(offer_date, 'strftime'):
        offer_date = offer_date.strftime('%B %d, %Y')

    # Format compensation
    if is_hourly:
        compensation_display = f"${offer_salary:,} / hour"
    else:
        compensation_display = f"{salary_currency} {offer_salary:,}"

    comp_label = "Hourly Rate" if is_hourly else "Salary"

    # ═══════════════════════════════════════════════════════════
    #  PAGE CONTENT
    # ═══════════════════════════════════════════════════════════

    # ── Opening paragraph ──────────────────────────────────
    story.append(Paragraph(
        f"Dear <b>{candidate_name}</b>,",
        style_body
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"We are pleased to extend this offer of employment for the position of "
        f"<b>{position_title}</b>. We were impressed by your qualifications and experience, "
        f"and we are confident that you will make a valuable contribution to our team.",
        style_body
    ))
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════
    #  OFFER DETAILS SECTION (with teal header bar)
    # ═══════════════════════════════════════════════════════════

    # Header row
    header_style = ParagraphStyle(
        'OfferHeader', parent=styles['Normal'],
        fontSize=12, textColor=white,
        fontName='Helvetica-Bold',
    )

    # Unicode icons as text substitutes
    icon_position = "🏢"
    icon_money = "💲"
    icon_calendar = "📅"
    icon_email = "✉"

    detail_rows = [
        [icon_position, "Position", position_title],
        [icon_money, comp_label, compensation_display],
        [icon_calendar, "Date of Joining", start_date if start_date else "To be confirmed"],
    ]

    if employer_email:
        detail_rows.append([icon_email, "Contact", employer_email])

    # Build table
    table_data = []

    # Header row
    table_data.append([
        Paragraph("OFFER DETAILS", header_style),
        '', ''
    ])

    # Detail rows
    for icon, label, value in detail_rows:
        table_data.append([
            Paragraph(f"  {icon}", ParagraphStyle(
                'Icon', parent=styles['Normal'],
                fontSize=12, alignment=TA_CENTER,
            )),
            Paragraph(label, style_label),
            Paragraph(f"<b>{value}</b>", style_value),
        ])

    col_widths = [0.5 * inch, 1.5 * inch, 4.2 * inch]

    detail_table = Table(table_data, colWidths=col_widths)
    detail_table.setStyle(TableStyle([
        # Header row styling
        ('BACKGROUND', (0, 0), (-1, 0), teal_dark),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('SPAN', (0, 0), (-1, 0)),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('LEFTPADDING', (0, 0), (-1, 0), 12),

        # Detail rows
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        ('LEFTPADDING', (0, 1), (0, -1), 8),
        ('LEFTPADDING', (1, 1), (1, -1), 4),
        ('LINEBELOW', (0, 1), (-1, -2), 0.5, border_gray),

        # Outer border
        ('BOX', (0, 0), (-1, -1), 0.5, border_gray),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),

        # Background for detail rows
        ('BACKGROUND', (0, 1), (-1, -1), bg_light),
    ]))

    story.append(detail_table)
    story.append(Spacer(1, 20))

    # ═══════════════════════════════════════════════════════════
    #  DESCRIPTION / ADDITIONAL TERMS (quote block style)
    # ═══════════════════════════════════════════════════════════

    if offer_terms:
        story.append(Paragraph(
            f"Description from <b>{company_name}</b>:",
            style_section_heading
        ))

        # Quote block using a table with left border
        quote_table = Table(
            [[Paragraph(f"<i>\"{offer_terms}\"</i>", style_quote)]],
            colWidths=[5.8 * inch],
        )
        quote_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), quote_bg),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LINEBELOW', (0, 0), (-1, -1), 0, white),
            # Left accent border
            ('LINEBEFORE', (0, 0), (0, -1), 3, quote_border),
        ]))
        story.append(quote_table)
        story.append(Spacer(1, 18))

    # ═══════════════════════════════════════════════════════════
    #  ACCEPTANCE PARAGRAPH
    # ═══════════════════════════════════════════════════════════

    story.append(Paragraph(
        "Please review the terms outlined above. If you choose to accept this offer, "
        "kindly confirm your acceptance by responding to this letter at your earliest "
        "convenience, but no later than <b>7 days</b> from the date of this letter.",
        style_body
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        f"We look forward to welcoming you to the <b>{company_name}</b> family "
        f"and beginning a rewarding professional journey together.",
        style_body
    ))
    story.append(Spacer(1, 24))

    # ═══════════════════════════════════════════════════════════
    #  SIGNATURE SECTION
    # ═══════════════════════════════════════════════════════════

    story.append(Paragraph("Warm regards,", style_body))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>{company_name}</b>", style_sig_name))
    story.append(Paragraph("Human Resources Department", style_sig_detail))
    if employer_email:
        story.append(Paragraph(employer_email, style_sig_detail))

    # ═══════════════════════════════════════════════════════════
    #  FOOTER
    # ═══════════════════════════════════════════════════════════

    story.append(Spacer(1, 40))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=border_gray, spaceAfter=8,
    ))
    story.append(Paragraph(
        f"This is an official offer letter from {company_name}. Powered by FLIT Platform.",
        style_footer
    ))

    # ── Build PDF ──────────────────────────────────────────
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    logger.info(
        f"Offer letter PDF generated for {candidate_name} - {position_title}"
    )
    return pdf_bytes
