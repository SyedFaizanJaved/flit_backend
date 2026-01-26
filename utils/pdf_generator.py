"""
PDF Generation utilities for generating resumes from CV data
"""
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def generate_pdf_from_cv_data(cv_data):
    """
    Generate PDF resume from CV JSON data using ReportLab
    
    Args:
        cv_data (dict): Dictionary containing CV data with keys like:
            - name: Candidate name
            - phone: Phone number
            - professional_summary: Professional summary text
            - online_profiles: Dict with linkedin, github, portfolio
            - experience: List of experience dicts
            - education: List of education dicts
            - skills: Dict with technical and soft skills
            - projects: List of project dicts
            - certifications: List of certification dicts
    
    Returns:
        bytes: PDF file content as bytes
    
    Raises:
        ImportError: If ReportLab is not installed
        Exception: If PDF generation fails
    """
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=6,
            spaceBefore=12
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.leading = 14
        
        # Name
        name = cv_data.get('name', '')
        if name:
            story.append(Paragraph(name, title_style))
            story.append(Spacer(1, 0.1*inch))
        
        # Contact Info
        phone = cv_data.get('phone', '')
        online_profiles = cv_data.get('online_profiles', {})
        contact_info = []
        if phone:
            contact_info.append(phone)
        if online_profiles.get('linkedin'):
            contact_info.append(f"LinkedIn: {online_profiles['linkedin']}")
        if online_profiles.get('github'):
            contact_info.append(f"GitHub: {online_profiles['github']}")
        if online_profiles.get('portfolio'):
            contact_info.append(f"Portfolio: {online_profiles['portfolio']}")
        
        if contact_info:
            story.append(Paragraph(' | '.join(contact_info), normal_style))
            story.append(Spacer(1, 0.2*inch))
        
        # Professional Summary
        professional_summary = cv_data.get('professional_summary', '')
        if professional_summary:
            story.append(Paragraph('<b>Professional Summary</b>', heading_style))
            story.append(Paragraph(professional_summary, normal_style))
            story.append(Spacer(1, 0.15*inch))
        
        # Experience
        experience = cv_data.get('experience', [])
        if experience:
            story.append(Paragraph('<b>Experience</b>', heading_style))
            for exp in experience:
                company = exp.get('company_name', '')
                position = exp.get('position', '')
                start_date = exp.get('start_date', '')
                end_date = exp.get('end_date', '')
                is_current = exp.get('is_current', False)
                description = exp.get('description', '')
                
                date_range = f"{start_date} - {end_date if not is_current else 'Present'}"
                exp_title = f"<b>{position}</b> at <b>{company}</b> | {date_range}"
                story.append(Paragraph(exp_title, normal_style))
                if description:
                    story.append(Paragraph(description, normal_style))
                story.append(Spacer(1, 0.1*inch))
            story.append(Spacer(1, 0.1*inch))
        
        # Education
        education = cv_data.get('education', [])
        if education:
            story.append(Paragraph('<b>Education</b>', heading_style))
            for edu in education:
                institution = edu.get('institution', '')
                degree = edu.get('degree', '')
                field_of_study = edu.get('field_of_study', '')
                start_date = edu.get('start_date', '')
                end_date = edu.get('end_date', '')
                gpa = edu.get('gpa', '')
                
                edu_parts = []
                if degree:
                    edu_parts.append(f"<b>{degree}</b>")
                if field_of_study:
                    edu_parts.append(f"in {field_of_study}")
                if institution:
                    edu_parts.append(f"from {institution}")
                
                edu_title = ' '.join(edu_parts)
                if start_date or end_date:
                    date_range = f"{start_date} - {end_date}" if end_date else start_date
                    edu_title += f" | {date_range}"
                if gpa:
                    edu_title += f" | GPA: {gpa}"
                
                story.append(Paragraph(edu_title, normal_style))
                story.append(Spacer(1, 0.1*inch))
            story.append(Spacer(1, 0.1*inch))
        
        # Skills
        skills = cv_data.get('skills', {})
        if skills:
            story.append(Paragraph('<b>Skills</b>', heading_style))
            technical = skills.get('technical', [])
            soft = skills.get('soft', [])
            
            if technical:
                story.append(Paragraph(f"<b>Technical:</b> {', '.join(technical)}", normal_style))
            if soft:
                story.append(Paragraph(f"<b>Soft Skills:</b> {', '.join(soft)}", normal_style))
            story.append(Spacer(1, 0.15*inch))
        
        # Projects
        projects = cv_data.get('projects', [])
        if projects:
            story.append(Paragraph('<b>Projects</b>', heading_style))
            for project in projects:
                if isinstance(project, dict):
                    title = project.get('title', '')
                    description = project.get('description', '')
                    if title:
                        story.append(Paragraph(f"<b>{title}</b>", normal_style))
                    if description:
                        story.append(Paragraph(description, normal_style))
                    story.append(Spacer(1, 0.1*inch))
            story.append(Spacer(1, 0.1*inch))
        
        # Certifications
        certifications = cv_data.get('certifications', [])
        if certifications:
            story.append(Paragraph('<b>Certifications</b>', heading_style))
            for cert in certifications:
                if isinstance(cert, dict):
                    cert_name = cert.get('name', '') or cert.get('title', '')
                    if cert_name:
                        story.append(Paragraph(f"• {cert_name}", normal_style))
                elif isinstance(cert, str):
                    story.append(Paragraph(f"• {cert}", normal_style))
            story.append(Spacer(1, 0.15*inch))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except ImportError:
        logger.error("ReportLab not installed. Please install it: pip install reportlab")
        raise
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        raise
