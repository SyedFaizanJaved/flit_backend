"""
PDF Generation utilities for generating resumes from CV data.
Output follows a professional resume template: clean layout, uppercase underlined
section headings, contact line, experience/education with right-aligned dates,
and two-column skills.
"""
import logging
from io import BytesIO
from datetime import datetime

logger = logging.getLogger(__name__)


def _format_date(s, default=''):
    """Format date string (YYYY-MM-DD or similar) to 'Mon YYYY' e.g. Jun 2018."""
    if not s or s == 'Present':
        return default or (s if s == 'Present' else '')
    try:
        part = str(s)[:10]
        d = datetime.strptime(part, '%Y-%m-%d')
        return d.strftime('%b %Y')
    except Exception:
        if len(str(s)) >= 7:
            return str(s)[:7]  # YYYY-MM
        return str(s)


def _section_heading_table(text, font_size=11):
    """Return a one-cell Table that looks like an underlined UPPERCASE heading."""
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    style = ParagraphStyle(
        'SectionHead',
        fontName='Times-Bold',
        fontSize=font_size,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=2,
        leftIndent=0,
        rightIndent=0,
    )
    p = Paragraph(f'<b>{text.upper()}</b>', style)
    # content_width: full content area so the underline runs across the page (Muhammad Husnain style)
    width = 7.3 * inch  # letter 8.5" - 0.6"*2 margins
    t = Table([[p]], colWidths=[width])
    t.setStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ])
    return t


def generate_pdf_from_cv_data(cv_data):
    """
    Generate a professional-style PDF resume from CV JSON data using ReportLab.

    Layout follows a standard professional template:
    - Name centered, contact line (Location • Phone • Email • LinkedIn)
    - UPPERCASE underlined section headings
    - Experience: Company, Location | Date (right); Job title; bullet points
    - Education: Institution, Location | Date (right); Degree in Field
    - Skills: two-column bullet list

    Args:
        cv_data (dict): CV data with keys: name, phone, email, location,
            professional_summary, online_profiles (linkedin, github, portfolio),
            experience, education, skills (technical, soft), projects, certifications.

    Returns:
        bytes: PDF file content as bytes.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
            leftMargin=0.6 * inch,
            rightMargin=0.6 * inch,
        )
        story = []

        styles = getSampleStyleSheet()
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName='Times-Roman',
            fontSize=10,
            leading=12,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=2,
            alignment=TA_LEFT,
            leftIndent=0,
        )
        # Word-style justified paragraphs for summary & descriptions (Muhammad Husnain professional look)
        justified_style = ParagraphStyle(
            'Justified',
            parent=normal_style,
            alignment=TA_JUSTIFY,
        )
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            fontName='Times-Bold',
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        contact_style = ParagraphStyle(
            'Contact',
            parent=styles['Normal'],
            fontName='Times-Roman',
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=14,
        )
        job_title_style = ParagraphStyle(
            'JobTitle',
            parent=normal_style,
            fontName='Times-Bold',
            fontSize=11,
            spaceAfter=1,
        )
        company_style = ParagraphStyle(
            'Company',
            parent=normal_style,
            fontName='Times-Italic',
            fontSize=10,
            spaceAfter=2,
        )
        bullet_style = ParagraphStyle(
            'Bullet',
            parent=normal_style,
            leftIndent=12,
            spaceAfter=2,
            bulletIndent=0,
            alignment=TA_LEFT,  # bullets stay left-aligned
        )

        # —— Header: Name + Contact line ——
        name = (cv_data.get('name') or '').strip()
        if name:
            story.append(Paragraph(name, title_style))
        contact_parts = []
        loc = (cv_data.get('location') or '').strip()
        if loc:
            contact_parts.append(loc)
        phone = (cv_data.get('phone') or '').strip()
        if phone:
            contact_parts.append(phone)
        email = (cv_data.get('email') or '').strip()
        if email:
            contact_parts.append(email)
        online = cv_data.get('online_profiles') or {}
        link = (online.get('linkedin') or '').strip()
        if link:
            if not link.startswith('http'):
                link = f"linkedin.com/in/{link}" if 'linkedin.com' not in link else link
            contact_parts.append(link)
        if contact_parts:
            story.append(Paragraph(' &bull; '.join(contact_parts), contact_style))
        else:
            story.append(Spacer(1, 0.05 * inch))

        # —— Professional Summary (optional) ——
        summary = (cv_data.get('professional_summary') or '').strip()
        if summary:
            story.append(Spacer(1, 0.08 * inch))
            story.append(_section_heading_table('Professional Summary'))
            story.append(Spacer(1, 0.06 * inch))
            story.append(Paragraph(summary.replace('\n', ' '), justified_style))
            story.append(Spacer(1, 0.15 * inch))

        # —— Professional Experience ——
        experience = cv_data.get('experience') or []
        if experience:
            story.append(Spacer(1, 0.1 * inch))
            story.append(_section_heading_table('Professional Experience'))
            story.append(Spacer(1, 0.08 * inch))

            for exp in experience:
                company = (exp.get('company') or '').strip()
                role = (exp.get('role') or '').strip()
                location = (exp.get('location') or '').strip()
                start_date = exp.get('start_date') or ''
                end_date = exp.get('end_date') or ''
                description = (exp.get('description') or '').strip()
                achievements = exp.get('achievements') or []

                date_range = _format_date(end_date, 'Present')
                if start_date:
                    date_str = f"{_format_date(start_date)} – {date_range}" if date_range else _format_date(start_date)
                else:
                    date_str = date_range or ''

                # Row 1: Role (Left, Bold) | Date (Right)
                # Row 2: Company, Location (Left, Italic)
                
                # Prepare Company string
                company_loc = company
                if location:
                    company_loc = f"{company}, {location}" if company else location
                if not company_loc:
                    company_loc = "—"

                # Table for Role + Date
                # Using full width 7.3 inch (5.5 + 1.8)
                para_role = Paragraph(f"<b>{role}</b>", job_title_style)
                para_date = Paragraph(date_str, ParagraphStyle('Right', parent=normal_style, alignment=TA_RIGHT))
                
                tbl = Table([[para_role, para_date]], colWidths=[5.5 * inch, 1.8 * inch])
                tbl.setStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                ])
                story.append(tbl)
                
                # Company line below
                story.append(Paragraph(company_loc, company_style))

                bullets = []
                if achievements and isinstance(achievements, list):
                    for a in achievements:
                        s = (a.get('text', a) if isinstance(a, dict) else str(a)).strip()
                        if s:
                            bullets.append(s)
                if not bullets and description:
                    for line in description.replace('\r\n', '\n').split('\n'):
                        line = line.strip()
                        if line:
                            bullets.append(line)
                    if not bullets:
                        bullets.append(description)
                for b in bullets:
                    story.append(Paragraph(f"• {b}", bullet_style))
                story.append(Spacer(1, 0.12 * inch))

            story.append(Spacer(1, 0.05 * inch))

        # —— Education ——
        education = cv_data.get('education') or []
        if education:
            story.append(_section_heading_table('Education'))
            story.append(Spacer(1, 0.08 * inch))

            for edu in education:
                institution = (edu.get('institution') or '').strip()
                degree = (edu.get('degree') or '').strip()
                field_of_study = (edu.get('field_of_study') or '').strip()
                start_date = edu.get('start_date') or ''
                end_date = edu.get('end_date') or ''
                gpa = edu.get('gpa')

                date_str = ''
                if start_date or end_date:
                    date_str = f"{_format_date(end_date) or 'Present'}"
                    if start_date:
                        date_str = f"{_format_date(start_date)} – {date_str}"

                inst_line = institution or "—"
                
                # Row 1: Institution (Bold) | Date (Right)
                para_inst = Paragraph(f"<b>{inst_line}</b>", job_title_style)
                para_date = Paragraph(date_str, ParagraphStyle('Right', parent=normal_style, alignment=TA_RIGHT))
                
                tbl = Table([[para_inst, para_date]], colWidths=[5.5 * inch, 1.8 * inch])
                tbl.setStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                ])
                story.append(tbl)

                degree_parts = []
                if degree:
                    degree_parts.append(degree)
                if field_of_study:
                    degree_parts.append(f"in {field_of_study}")
                if degree_parts:
                    line = ' '.join(degree_parts)
                    if gpa is not None and str(gpa).strip():
                        line += f"; GPA: {gpa}"
                    story.append(Paragraph(line, company_style))
                story.append(Spacer(1, 0.1 * inch))
            story.append(Spacer(1, 0.05 * inch))

        # —— Skills (two-column bullet list) ——
        skills = cv_data.get('skills') or {}
        technical = skills.get('technical') or []
        soft = skills.get('soft') or []
        if isinstance(technical, str):
            technical = [s.strip() for s in technical.split(',') if s.strip()]
        if isinstance(soft, str):
            soft = [s.strip() for s in soft.split(',') if s.strip()]
        all_skills = [str(s).strip() for s in technical] + [str(s).strip() for s in soft]
        all_skills = [s for s in all_skills if s]

        if all_skills:
            story.append(_section_heading_table('Skills'))
            story.append(Spacer(1, 0.06 * inch))
            # Split into two columns
            n = (len(all_skills) + 1) // 2
            left_items = all_skills[:n]
            right_items = all_skills[n:]
            left_paras = [Paragraph(f"• {s}", bullet_style) for s in left_items]
            right_paras = [Paragraph(f"• {s}", bullet_style) for s in right_items]
            max_rows = max(len(left_paras), len(right_paras))
            while len(left_paras) < max_rows:
                left_paras.append(Paragraph(' ', normal_style))
            while len(right_paras) < max_rows:
                right_paras.append(Paragraph(' ', normal_style))
            skill_table = Table(
                list(zip(left_paras, right_paras)),
                colWidths=[3.65 * inch, 3.65 * inch],
            )
            skill_table.setStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (0, -1), 0),
                ('LEFTPADDING', (1, 0), (1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ])
            story.append(skill_table)
            story.append(Spacer(1, 0.15 * inch))

        # —— Projects ——
        projects = cv_data.get('projects') or []
        if projects:
            story.append(_section_heading_table('Projects'))
            story.append(Spacer(1, 0.06 * inch))
            for proj in projects:
                if isinstance(proj, dict):
                    title = (proj.get('title') or '').strip()
                    desc = (proj.get('description') or '').strip()
                else:
                    title, desc = str(proj).strip(), ''
                if title:
                    story.append(Paragraph(f'<b>{title}</b>', job_title_style))
                if desc:
                    story.append(Paragraph(desc.replace('\n', ' '), justified_style))
                story.append(Spacer(1, 0.08 * inch))
            story.append(Spacer(1, 0.05 * inch))

        # —— Certifications ——
        certifications = cv_data.get('certifications') or []
        if certifications:
            story.append(_section_heading_table('Certifications'))
            story.append(Spacer(1, 0.06 * inch))
            for cert in certifications:
                text = ''
                if isinstance(cert, dict):
                    text = (cert.get('name') or cert.get('title') or '').strip()
                elif isinstance(cert, str):
                    text = cert.strip()
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            story.append(Spacer(1, 0.1 * inch))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    except ImportError:
        logger.error("ReportLab not installed. Please install it: pip install reportlab")
        raise
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        raise
