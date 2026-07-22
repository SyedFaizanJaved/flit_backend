"""
Email service module for sending professional email notifications
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


# Common No-Reply Notice
NO_REPLY_TEXT = """

---
PLEASE DO NOT REPLY TO THIS EMAIL. 
This is an automated message sent from an unmonitored mailbox. 
Replies to this email will not be received or reviewed.
"""

NO_REPLY_HTML = """
            <div class="no-reply-box">
                <strong>🚫 PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                This is an automated message sent from an unmonitored mailbox. 
                Replies to this email will not be received or reviewed.
            </div>
"""


def get_base_url():
    """Get the base frontend URL from settings"""
    return getattr(settings, 'FLIT_REQUEST_URL')


def get_logo_url():
    """Get the logo URL for email templates"""
    base_url = get_base_url()
    return f"{base_url}/email-logo.png"


def get_email_styles():
    """Common CSS styles for email templates"""
    return """
        body {
            margin: 0;
            padding: 0;
            font-family: 'Arial', sans-serif;
            line-height: 1.6;
            color: #333333;
            background-color: #f4f7fa;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            border: 2px solid #e0e6ed;
        }
        .header {
            background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);
            padding: 30px;
            text-align: center;
            color: white;
            position: relative;
            border-bottom: 2px solid #e0e6ed;
        }
        .logo {
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 10px;
        }
        .logo img {
            height: 40px;
            width: auto;
            
        }
        .logo-text {
            font-family: 'Montserrat', 'Arial', sans-serif;
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 0.05em;
            color: white;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .header-title {
            font-size: 24px;
            margin: 0;
            font-weight: 600;
            color: #ffffff;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
        }
        .content {
            background-color: #ffffff;
            padding: 40px;
            border: 1px solid #e0e6ed;
            border-top: none;
            border-bottom: none;
        }
        .greeting {
            font-size: 18px;
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .info-box {
            background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 5px solid #3498db;
            border: 1px solid #e0e6ed;
        }
        .info-box h3 {
            margin: 0 0 10px 0;
            color: #2c3e50;
            font-size: 16px;
        }
        .info-box p {
            margin: 5px 0;
            color: #555;
        }
        .message {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #3498db;
            font-style: italic;
            border: 1px solid #e0e6ed;
        }
        .footer {
            background-color: #34495e;
            color: #ffffff;
            padding: 25px;
            text-align: center;
            font-size: 14px;
            border-top: 2px solid #e0e6ed;
        }
        .no-reply-box {
            background-color: #fff3f3;
            border: 1px solid #ffcccc;
            color: #d63031;
            padding: 15px;
            margin: 25px 0 0 0;
            border-radius: 8px;
            text-align: center;
            font-size: 13px;
            line-height: 1.4;
        }
        .no-reply-box strong {
            color: #c0392b;
            display: block;
            margin-bottom: 5px;
            font-size: 15px;
        }
        @media only screen and (max-width: 600px) {
            .container { border-radius: 0; }
            .content { padding: 20px; }
        }
    """


def send_email(to_email, subject, text_content, html_content):
    """
    Send an email with both plain text and HTML content
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        text_content: Plain text version of the email
        html_content: HTML version of the email
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@flit.com')
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content.strip(),
            from_email=from_email,
            to=[to_email],
            reply_to=[from_email]
        )
        
        # Attach the HTML version
        msg.attach_alternative(html_content, "text/html")
        
        # Send the email
        msg.send()
        
        logger.info(f"Email sent successfully to {to_email} with subject: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        return False


def send_shortlist_notification(candidate, job_or_project_title, application_type='job', company_name=None):
    """
    Send email notification when a candidate is shortlisted
    
    Args:
        candidate: Candidate model instance
        job_or_project_title: Title of the job or project
        application_type: 'job' or 'project'
        company_name: Name of the company (optional)
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"
    view_url = f"{base_url}/candidate/dashboard?tab=applications"
    
    application_type_label = 'Job' if application_type == 'job' else 'Project'
    
    subject = f"Congratulations! You've been shortlisted for {job_or_project_title}"
    
    frame_icon_url = f"{base_url}/star.png"
    company_display = f"<strong>{company_name}</strong> has" if company_name else "An employer has"
    
    # Plain text version
    text_content = f"""
Hello {candidate_name},

Congratulations, {candidate_name}! {company_name or 'An employer'} has shortlisted you for the {job_or_project_title} role. This means your profile stood out, here's what's next.

OPPORTUNITY DETAILS:
Role: {job_or_project_title}
Company: {company_name or 'N/A'}
Type: {application_type_label}
Status: Shortlisted

We recommend reviewing the opportunity details and ensuring your profile is up to date. The employer may reach out for next steps soon.

View Application: {view_url}

Need help? Contact Support: {support_url}
© 2026 FLIT · Where talent meets opportunity
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #dce8f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #1e3a7b;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #e8faed;
            border-radius: 50%;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
        }}
        .badge-icon img {{
            display: inline-block;
            vertical-align: middle;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #27ae60;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 16px;
            line-height: 28.8px;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #3d3d5c;
            margin-bottom: 24px;
        }}

        .detail-box {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .detail-box-title {{
            font-size: 11px;
            font-weight: 700;
            color: #7a7a99;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .detail-table td {{
            padding: 14px 0;
            border-bottom: 1px solid #eef0f5;
            font-size: 14px;
            color: #7a7a99;
        }}
        .detail-table tr:last-child td {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .detail-value {{
            text-align: right;
            color: #14181f !important;
            font-weight: 600;
        }}

        .btn-wrap {{
            text-align: center;
            margin-bottom: 28px;
            margin-top: 24px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #1e3a7b;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 40px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        .fallback-text {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 12px;
            line-height: 1.6;
        }}
        
        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
            background-color: #dce8f5;
        }}
        .footer-support {{
            font-size: 13px;
            color: #3d3d5c;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 4px;
        }}
        .footer-auto {{
            font-size: 11px;
            color: #b0b0c8;
        }}
        
        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #b91c1c;
            line-height: 1.6;
            text-align: center;
            margin-top: 16px;
            margin-bottom: 24px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #8b0000;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{frame_icon_url}" alt="Good News" width="24" height="24" style="display:inline-block; vertical-align:middle;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none; font-size: 20px;">⭐</span>
                    </div>
                    <span class="badge-label">GOOD NEWS</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">You've Been Shortlisted</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Congratulations, <span style="font-weight: 700; color: #1e3a7b;">{candidate_name}!</span> {company_display} shortlisted you for the {job_or_project_title} role. This means your profile stood out, here's what's next.
                </p>

                <!-- Detail Box -->
                <div class="detail-box">
                    <div class="detail-box-title">OPPORTUNITY DETAILS</div>
                    <table class="detail-table">
                        <tr>
                            <td>Role</td>
                            <td class="detail-value">{job_or_project_title}</td>
                        </tr>
                        <tr>
                            <td>Company</td>
                            <td class="detail-value">{company_name or 'Not specified'}</td>
                        </tr>
                        <tr>
                            <td>Type</td>
                            <td class="detail-value">{application_type_label}</td>
                        </tr>
                        <tr>
                            <td>Status</td>
                            <td class="detail-value"><span style="color: #2ecc71;">✅</span> Shortlisted</td>
                        </tr>
                    </table>
                </div>

                <p class="email-text" style="color: #666687;">
                    We recommend reviewing the opportunity details and ensuring your profile is up to date. The employer may reach out for next steps soon.
                </p>

                <!-- CTA -->
                <div class="btn-wrap">
                    <a href="{view_url}" class="cta-button">View Application</a>
                </div>

                <p class="fallback-text">
                    You're receiving this because you applied to this role on FLIT. Further updates will follow as the process progresses.
                </p>

                <!-- Red Notice box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed
                </div>

            </div><!-- /email-body -->

        </div>
        
        <!-- Footer explicitly out of card in this Figma design but inside wrapper? Wait, the Figma design shows it below the card -->
        <div class="email-footer">
            <p class="footer-support">
                Need help?&nbsp;<a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT &middot; Where talent meets opportunity</p>
            <p class="footer-auto">This is an automated message. Please do not reply directly.</p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(candidate_email, subject, text_content, html_content)


def send_rejection_notification(candidate, job_or_project_title, application_type='job', rejection_reason=None, company_name=None):
    """
    Send email notification when a candidate is rejected
    
    Args:
        candidate: Candidate model instance
        job_or_project_title: Title of the job or project
        application_type: 'job' or 'project'
        rejection_reason: Optional rejection reason message
        company_name: Optional company name
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name or "Candidate"
    candidate_first_name = candidate_name.split()[0]
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"
    jobs_url = f"{base_url}/candidate/opportunities"
    
    application_type_label = 'Job' if application_type == 'job' else 'Project'
    
    subject = "An Update on Your Application"
    
    company_display_html = f" at <strong>{company_name}</strong>" if company_name else ""
    company_display_text = f" at {company_name}" if company_name else ""
    reject_icon_url = f"{base_url}/reject.png"
    
    # Plain text version
    text_content = f"""
Hello {candidate_first_name},

Thank you for your interest in the {job_or_project_title} role{company_display_text}. We appreciate the time and effort you put into your application.

APPLICATION DETAILS:
Position: {job_or_project_title}
Company: {company_name or 'N/A'}
Type: {application_type_label}
Status: Not Selected

After careful review, the team has decided to move forward with other candidates for this particular role. This doesn't reflect on your skills or potential, hiring decisions involve many factors, and the right match is out there.

{f'Note: {rejection_reason}' if rejection_reason else ''}

Browse More Opportunities: {jobs_url}

We encourage you to keep your profile active and explore new opportunities on FLIT. New roles are posted regularly, and your next match could be just around the corner.

Need help? Contact Support: {support_url}
© 2026 FLIT · Where talent meets opportunity
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #dce8f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #1e3a7b;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #f3f4f6;
            border-radius: 8px;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
            font-size: 18px;
            color: #6b7280;
            font-weight: 500;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #6b7280;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 24px;
            line-height: 1.2;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #3d3d5c;
            margin-bottom: 24px;
        }}

        .detail-box {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .detail-box-title {{
            font-size: 11px;
            font-weight: 700;
            color: #7a7a99;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .detail-table td {{
            padding: 14px 0;
            border-bottom: 1px solid #eef0f5;
            font-size: 14px;
            color: #7a7a99;
        }}
        .detail-table tr:last-child td {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .detail-value {{
            text-align: right;
            color: #14181f !important;
            font-weight: 600;
        }}

        .btn-wrap {{
            text-align: center;
            margin-bottom: 28px;
            margin-top: 24px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #435185;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 24px;
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        .gray-notice-box {{
            background-color: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 24px;
            font-size: 13px;
            color: #6b7280;
            line-height: 1.6;
            text-align: left;
            margin-top: 16px;
            margin-bottom: 24px;
        }}
        
        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #b91c1c;
            line-height: 1.6;
            text-align: center;
            margin-top: 24px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #8b0000;
        }}

        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
            background-color: #dce8f5;
        }}
        .footer-support {{
            font-size: 13px;
            color: #3d3d5c;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 4px;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" onerror="this.style.display='none';" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{reject_icon_url}" alt="Application Update" width="42" height="42" style="display:inline-block; vertical-align:middle;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none;">&#8594;</span>
                    </div>
                    <span class="badge-label">APPLICATION UPDATE</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">An Update on Your Application</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Hi {candidate_first_name}, thank you for your interest in the <span style="font-weight: 700; color: #14181f;">{job_or_project_title}</span> role{company_display_html}. We appreciate the time and effort you put into your application.
                </p>

                <!-- Detail Box -->
                <div class="detail-box">
                    <div class="detail-box-title">APPLICATION DETAILS</div>
                    <table class="detail-table">
                        <tr>
                            <td>Position</td>
                            <td class="detail-value">{job_or_project_title}</td>
                        </tr>
                        <tr>
                            <td>Company</td>
                            <td class="detail-value">{company_name or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td>Type</td>
                            <td class="detail-value">{application_type_label}</td>
                        </tr>
                        <tr>
                            <td>Status</td>
                            <td class="detail-value" style="color: #4b5563;">Not Selected</td>
                        </tr>
                    </table>
                </div>

                <p class="email-text">
                    After careful review, the team has decided to move forward with other candidates for this particular role. This doesn't reflect on your skills or potential, hiring decisions involve many factors, and the right match is out there.
                </p>
                
                {f'<p class="email-text" style="color: #6b7280;"><strong>Note:</strong> {rejection_reason}</p>' if rejection_reason else ''}

                <!-- CTA -->
                <div class="btn-wrap">
                    <a href="{jobs_url}" class="cta-button">Browse More Opportunities</a>
                </div>

                <!-- Encouragement Box -->
                <div class="gray-notice-box">
                    We encourage you to keep your profile active and explore new opportunities on FLIT. New roles are posted regularly, and your next match could be just around the corner.
                </div>

                <!-- Red Notice box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed.
                </div>

            </div><!-- /email-body -->

        </div>
        
        <!-- Footer -->
        <div class="email-footer">
            <p class="footer-support">
                Need help?&nbsp;<a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT - Where talent meets opportunity</p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(candidate_email, subject, text_content, html_content)


def send_flit_pass_notification(candidate, employer_name, company_name=None, category=None):
    """
    Send email notification when an employer flits (likes/saves) a candidate profile
    
    Args:
        candidate: Candidate model instance
        employer_name: Name of the employer who flitted the profile
        company_name: Optional company name
        category: Optional category or industry
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name or "Candidate"
    candidate_first_name = candidate_name.split()[0]
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"
    view_url = f"{base_url}/candidate/dashboard?tab=flit-list"
    
    subject = "Your Profile got FLIT"
    
    display_employer = company_name if company_name else employer_name
    display_category = category if category else "Not specified"
    stars_icon_url = f"{base_url}/stars.png"
    
    # Plain text version
    text_content = f"""
Great news, {candidate_first_name}! An employer on FLIT showed interest in your profile. Your skills and experience stood out, and this could be the start of something exciting.

INTEREST DETAILS:
Employer: {display_employer}
Category: {display_category}
Interest: ⭐ Profile Interest

Employers who show interest are often looking to connect soon. Make sure your profile is up to date and keep an eye out for messages or interview requests.

View Activity: {view_url}

This is an automated email, so replies won't be seen. If you need help, please contact our support team: {support_url}
© 2026 FLIT · Where talent meets opportunity
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #eef0f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #3b82f6;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: transparent;
            border-radius: 8px;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #435185;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 24px;
            line-height: 1.2;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #6b7280;
            margin-bottom: 24px;
        }}

        .detail-box {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .detail-box-title {{
            font-size: 11px;
            font-weight: 700;
            color: #7a7a99;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .detail-table td {{
            padding: 14px 0;
            border-bottom: 1px solid #eef0f5;
            font-size: 14px;
            color: #7a7a99;
        }}
        .detail-table tr:last-child td {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .detail-value {{
            text-align: right;
            color: #14181f !important;
            font-weight: 600;
        }}

        .btn-wrap {{
            text-align: center;
            margin-bottom: 28px;
            margin-top: 24px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #435185;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 24px;
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #c81e1e;
            line-height: 1.6;
            text-align: center;
            margin-top: 16px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #c81e1e;
        }}

        .card-footer {{
            border-top: 1px solid #eef0f5;
            padding-top: 24px;
            margin-top: 32px;
            font-size: 13px;
            color: #9ca3af;
            text-align: left;
            line-height: 1.5;
        }}
        .card-footer a {{
            color: #3b82f6;
            text-decoration: none;
        }}

        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
            background-color: #eef0f5;
        }}
        .footer-support {{
            font-size: 13px;
            color: #9ca3af;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #3b82f6;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 4px;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" onerror="this.style.display='none';" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{stars_icon_url}" alt="Profile Interest" width="42" height="42" style="display:inline-block; vertical-align:middle;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none; color: #435185; font-size: 24px;">✨</span>
                    </div>
                    <span class="badge-label">PROFILE INTEREST</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">Your Profile got FLIT</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Great news, <span style="font-weight: 700; color: #435185;">{candidate_first_name}!</span> An employer on FLIT showed interest in your profile. Your skills and experience stood out, and this could be the start of something exciting.
                </p>

                <!-- Detail Box -->
                <div class="detail-box">
                    <div class="detail-box-title">INTEREST DETAILS</div>
                    <table class="detail-table">
                        <tr>
                            <td>Employer</td>
                            <td class="detail-value">{display_employer}</td>
                        </tr>
                        <tr>
                            <td>Category</td>
                            <td class="detail-value">{display_category}</td>
                        </tr>
                        <tr>
                            <td>Interest</td>
                            <td class="detail-value">&#11088; Profile Interest</td>
                        </tr>
                    </table>
                </div>

                <p class="email-text">
                    Employers who show interest are often looking to connect soon. Make sure your profile is up to date and keep an eye out for messages or interview requests.
                </p>
                
                <!-- CTA -->
                <div class="btn-wrap">
                    <a href="{view_url}" class="cta-button">View Activity</a>
                </div>

                <!-- Red Notice box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed.
                </div>

            </div><!-- /email-body -->

        </div>
        
        <!-- Footer -->
        <div class="email-footer">
            <p class="footer-support">
                Need help?&nbsp;<a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT · Where talent meets opportunity</p>
            <p class="footer-copy" style="font-size: 11px;">This is an automated message. Please do not reply directly.</p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(candidate_email, subject, text_content, html_content)


def send_chat_message_notification(sender, recipient, message_content):
    """
    Send email notification when a user receives a chat message
    
    Args:
        sender: User model instance (sender)
        recipient: User model instance (recipient)
        message_content: The content of the message
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    recipient_name = getattr(recipient, 'first_name', None) or recipient.username
    if not recipient_name.strip():
        recipient_name = recipient.username
        
    sender_full = getattr(sender, 'first_name', None) or sender.username
    if getattr(sender, 'last_name', None):
        sender_full += f" {sender.last_name}"
    
    sender_first = getattr(sender, 'first_name', None) or sender.username
    if not sender_first:
        sender_first = "User"
    sender_initial = sender_first[0].upper() if sender_first else "U"
    
    recipient_email = recipient.email
    
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"
    chat_url = f"{base_url}/candidate/dashboard"
    
    try:
        if hasattr(recipient, 'employer_profile'):
            chat_url = f"{base_url}/employer/dashboard"
    except Exception:
        pass
        
    company_name = ""
    sender_subtitle = "FLIT User"
    try:
        if hasattr(sender, 'employer_profile'):
            company = sender.employer_profile.company
            if company:
                company_name = company.company_name
                sender_subtitle = f"Employer · {company_name}"
            else:
                sender_subtitle = "Employer"
        elif hasattr(sender, 'candidate_profile'):
            title = getattr(sender.candidate_profile, 'job_title', None)
            sender_subtitle = title if title else "Candidate"
    except Exception:
        pass
        
    sender_display = f"{sender_first} from {company_name}" if company_name else f"{sender_first}"
    
    subject = f"A New Message Is Waiting for You"
    message_icon_url = f"{base_url}/Vector.png"
    
    import datetime
    current_time = datetime.datetime.now().strftime("%I:%M %p")
    
    # Plain text version
    text_content = f"""
Hi {recipient_name}, {sender_display} sent you a message on FLIT. Don't keep them waiting, check it out and keep the conversation going.

From: {sender_full} ({sender_subtitle})
Message: "{message_content}"
Time: {current_time}

Timely responses help you stand out to employers. Head over to FLIT to read the full message and reply.

This is an automated email, so replies won't be seen. If you need help, please contact our support team.
© 2026 FLIT · Where talent meets opportunity
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #eef0f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #3b82f6;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #e0f2fe;
            border-radius: 8px;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #3b82f6;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 24px;
            line-height: 1.2;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #4b5563;
            margin-bottom: 24px;
        }}

        .message-card {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .message-header {{
            margin-bottom: 16px;
        }}
        .avatar {{
            width: 40px;
            height: 40px;
            background-color: #e0e7ff;
            color: #1e3a8a;
            border-radius: 50%;
            display: inline-block;
            vertical-align: middle;
            text-align: center;
            line-height: 40px;
            font-weight: 700;
            font-size: 16px;
            margin-right: 12px;
        }}
        .sender-info {{
            display: inline-block;
            vertical-align: middle;
        }}
        .sender-name {{
            font-weight: 700;
            color: #14181f;
            font-size: 14px;
        }}
        .sender-subtitle {{
            font-size: 12px;
            color: #9ca3af;
            margin-top: 2px;
        }}
        .message-body {{
            background-color: #f3f4f6;
            border-left: 3px solid #3b82f6;
            padding: 16px;
            border-radius: 0 8px 8px 0;
            font-size: 14px;
            color: #4b5563;
            line-height: 1.6;
            margin-bottom: 12px;
        }}
        .message-time {{
            text-align: right;
            font-size: 11px;
            color: #9ca3af;
        }}

        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #b91c1c;
            line-height: 1.6;
            text-align: center;
            margin-top: 24px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #8b0000;
        }}

        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
            background-color: #eef0f5;
        }}
        .footer-support {{
            font-size: 13px;
            color: #9ca3af;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #3b82f6;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 4px;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" onerror="this.style.display='none';" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{message_icon_url}" alt="New Message" width="20" height="20" style="vertical-align: middle; margin-top: -3px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none; color: #3b82f6; font-size: 20px; vertical-align: middle;">💬</span>
                    </div>
                    <span class="badge-label">NEW MESSAGE</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">A New Message Is Waiting for You</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Hi {recipient_name}, <span style="font-weight: 700; color: #14181f;">{sender_display}</span> sent you a message on FLIT. Don't keep them waiting, check it out and keep the conversation going.
                </p>

                <!-- Message Card -->
                <div class="message-card">
                    <div class="message-header">
                        <div class="avatar">{sender_initial}</div>
                        <div class="sender-info">
                            <div class="sender-name">{sender_full}</div>
                            <div class="sender-subtitle">{sender_subtitle}</div>
                        </div>
                    </div>
                    <div class="message-body">
                        "{message_content}"
                    </div>
                    <div class="message-time">{current_time}</div>
                </div>

                <p class="email-text">
                    Timely responses help you stand out to employers. Head over to FLIT to read the full message and reply.
                </p>

                <!-- CTA Button Omitted per user request -->

                <!-- Red Notice box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed.
                </div>

            </div><!-- /email-body -->

        </div>
        
        <!-- Footer -->
        <div class="email-footer">
            <p class="footer-support">
                Need help?&nbsp;<a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT · Where talent meets opportunity</p>
            <p class="footer-copy" style="font-size: 11px;">This is an automated message. Please do not reply directly.</p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(recipient_email, subject, text_content, html_content)


def send_verification_email(user, verification_url):
    """
    Send email verification email with a clean, professional styled template
    matching the FLIT brand design guidelines.
    
    Args:
        user: User model instance
        verification_url: The verification URL with token
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    user_name = user.first_name or user.username
    user_email = user.email
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"

    # Truncate long token URL for display only (keep full URL in href)
    display_url = verification_url if len(verification_url) <= 55 else verification_url[:52] + "..."

    # Frame icon URL from frontend public folder
    frame_icon_url = f"{base_url}/verified.png"

    subject = 'Verify your FLIT email address'

    # Plain text fallback
    text_content = f"""
Hello {user_name},

Thanks for creating your profile on FLIT, {user_name}.
Click the link below to verify your email and unlock your full profile.
This link expires in 15 minutes.

{verification_url}

This link expires in 15 minutes. If you didn't create an account on FLIT,
you can safely ignore this email.

Need help? Contact Support: {support_url}

© 2026 FLIT · Where talent meets opportunity
This is an automated message. Please do not reply directly.
"""

    # HTML version — pixel-perfect match to the new design
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #dce8f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        /* ── Outer wrapper ─────────────────────────────── */
        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        /* ── Card ──────────────────────────────────────── */
        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #1e3a7b; /* Bold top border only */
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        /* ── Header (logo row) ─────────────────────────── */
        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}
        .logo-wordmark {{
            font-size: 22px;
            font-weight: 700;
            color: #1e3a7b;
            letter-spacing: -0.3px;
        }}

        /* ── Body ──────────────────────────────────────── */
        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        /* badge row */
        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #eef2fb;
            border-radius: 50%;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
        }}
        .badge-icon img {{
            display: inline-block;
            vertical-align: middle;
            margin-top: -3px;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #1e3a7b;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        /* heading */
        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 16px;
            line-height: 28.8px;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        /* body text */
        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #3d3d5c;
            margin-bottom: 28px;
        }}
        .email-text .highlight-name {{
            color: #1e3a7b;
            font-weight: 700;
        }}

        /* CTA button */
        .btn-wrap {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #1e3a7b;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 40px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        /* fallback link */
        .fallback-text {{
            font-size: 12.5px;
            color: #7a7a99;
            margin-bottom: 24px;
            line-height: 1.6;
        }}
        .fallback-text a {{
            color: #1e3a7b;
            word-break: break-all;
        }}

        /* notice box */
        .notice-box {{
            background-color: #f5f6fa;
            border-radius: 8px;
            padding: 14px 18px;
            font-size: 13px;
            color: #4a4a6a;
            line-height: 1.6;
            display: flex;
            gap: 10px;
            align-items: flex-start;
        }}
        .notice-icon {{
            font-size: 15px;
            flex-shrink: 0;
            margin-top: 1px;
        }}
        
        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #b91c1c;
            line-height: 1.6;
            text-align: center;
            margin-top: 16px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #8b0000;
        }}

        /* ── Footer ────────────────────────────────────── */
        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
        }}
        .footer-support {{
            font-size: 13.5px;
            color: #3d3d5c;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 4px;
        }}
        .footer-auto {{
            font-size: 11px;
            color: #b0b0c8;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
            .email-heading {{ font-size: 22px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card-top-border"></div>
        <div class="card">

            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{frame_icon_url}" alt="Account Verification" width="24" height="24" style="display:inline-block; vertical-align:middle;" />
                    </div>
                    <span class="badge-label">Account Verification</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">Verify Your Email</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Thanks for creating your profile on FLIT,
                    <span class="highlight-name">{user_name}</span>.
                    Click below to verify your email and unlock your full profile.
                    This link expires in 15 minutes.
                </p>

                <!-- CTA -->
                <div class="btn-wrap">
                    <a href="{verification_url}" class="cta-button">Verify Email Address</a>
                </div>

                <!-- Notice box -->
                <div class="notice-box">
                    <span class="notice-icon">&#128274;</span>
                    <span>
                        This link expires in 15 minutes. If you didn't create an account on FLIT,
                        you can safely ignore this email.
                    </span>
                </div>

                <!-- Red Notice box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed.
                </div>

            </div><!-- /email-body -->
        </div><!-- /card -->

        <!-- Footer -->
        <div class="email-footer">
            <p class="footer-support">
                Need help?&nbsp;<a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT &middot; Where talent meets opportunity</p>
            <p class="footer-auto">This is an automated message. Please do not reply directly.</p>
        </div>
    </div><!-- /wrapper -->
</body>
</html>
"""

    return send_email(user_email, subject, text_content, html_content)


def send_offer_letter_email(candidate, company_name, position_title, offer_salary,
                            salary_currency, start_date, employment_type,
                            location, offer_terms, pdf_bytes):
    """
    Send offer letter email with PDF attachment to the hired candidate.

    Args:
        candidate: Candidate model instance
        company_name: Name of the hiring company
        position_title: The offered position title
        offer_salary: Salary amount (int)
        salary_currency: Currency code (str)
        start_date: Start date (str)
        employment_type: Type of employment (str)
        location: Work location (str)
        offer_terms: Additional offer terms (str, optional)
        pdf_bytes: Generated PDF file content (bytes)

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    styles = get_email_styles()
    base_url = get_base_url()

    formatted_salary = f"{salary_currency} {offer_salary:,}"
    emp_type_display = employment_type.replace('-', ' ').title()

    # Format start_date for display
    if hasattr(start_date, 'strftime'):
        start_date_display = start_date.strftime('%B %d, %Y')
    else:
        start_date_display = str(start_date)

    subject = f"🎉 Congratulations! Offer Letter from {company_name} — {position_title}"
    support_url = f"{base_url}/support"
    meddle_icon_url = f"{base_url}/medlle.png"

    # Plain text version
    text_content = f"""
Hello {candidate_name},

Congratulations! We are thrilled to inform you that you have been selected for the position of {position_title} at {company_name}.

Offer Details:
- Position: {position_title}
- Employment Type: {emp_type_display}
- Compensation: {formatted_salary}
- Start Date: {start_date_display}
- Location: {location or 'To be determined'}

{f'Additional Terms: {offer_terms}' if offer_terms else ''}

Please find your official offer letter attached as a PDF document.

We are excited about the possibility of you joining our team and look forward to working with you!

Best regards,
The {company_name} Team
(Powered by {getattr(settings, 'SITE_NAME', 'FLIT')})
"""

    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #f3f4f6;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card-top-border {{
            height: 4px;
            background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
            border-radius: 8px 8px 0 0;
        }}

        .card {{
            background: #ffffff;
            border-radius: 0 0 8px 8px;
            overflow: hidden;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.05);
        }}

        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #eef2fb;
            border-radius: 50%;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
        }}
        .badge-icon img {{
            display: inline-block;
            vertical-align: middle;
            margin-top: -3px;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #1e3a7b;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 16px;
            line-height: 28.8px;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 14.5px;
            line-height: 1.7;
            color: #4b5563;
            margin-bottom: 24px;
        }}
        
        .highlight-name {{
            color: #1e3a7b;
            font-weight: 700;
        }}

        .detail-box {{
            background-color: #ffffff;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 18px 24px;
            margin-bottom: 24px;
        }}
        .detail-box-title {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #1e3a7b;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .detail-table td {{
            padding: 12px 0;
            border-bottom: 1px solid #f8f9fa;
            font-size: 13.5px;
            color: #6b7280;
        }}
        .detail-table tr:last-child td {{
            border-bottom: none;
        }}
        .detail-value {{
            color: #111827;
            font-weight: 600;
            text-align: right;
        }}
        
        .offer-desc-box {{
            background-color: #f9fafb;
            border-radius: 8px;
            padding: 20px 24px;
            margin-bottom: 24px;
        }}
        .offer-desc-title {{
            font-size: 13.5px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 8px;
        }}
        .offer-desc-text {{
            font-size: 14px;
            color: #6b7280;
            line-height: 1.6;
        }}

        .btn-wrap {{
            text-align: center;
            margin-top: 8px;
            margin-bottom: 32px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #3b426e;
            color: #ffffff !important;
            text-decoration: none;
            padding: 13px 36px;
            border-radius: 30px;
            font-size: 14.5px;
            font-weight: 600;
            margin-bottom: 16px;
        }}
        
        .secondary-link {{
            display: block;
            font-size: 14px;
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
            margin-top: 8px;
        }}

        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #c81e1e;
            line-height: 1.6;
            text-align: center;
            margin-bottom: 24px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #c81e1e;
        }}

        .note-box {{
            border-top: 1px solid #eef0f5;
            padding-top: 20px;
            font-size: 11.5px;
            line-height: 1.6;
            color: #9ca3af;
        }}

        .email-footer {{
            padding: 24px 36px;
            text-align: center;
            background-color: transparent;
        }}
        .footer-support {{
            font-size: 13.5px;
            color: #6b7280;
            margin-bottom: 8px;
        }}
        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 4px;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
            .email-heading {{ font-size: 22px; }}
            .detail-box, .offer-desc-box {{ padding-left: 16px; padding-right: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card-top-border"></div>
        <div class="card">
            
            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" onerror="this.style.display='none';" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{meddle_icon_url}" alt="Offer Received" width="24" height="24" style="display:inline-block; vertical-align:middle;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none; font-size: 20px;">⭐</span>
                    </div>
                    <span class="badge-label">OFFER RECEIVED</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">You've Received an Offer!</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Congratulations <span class="highlight-name">{candidate_name}</span> {company_name} has extended a formal offer to you through FLIT. Review the details below and take the next step.
                </p>

                <!-- Details Box -->
                <div class="detail-box">
                    <div class="detail-box-title">OFFER DETAILS</div>
                    <table class="detail-table">
                        <tr>
                            <td>Position</td>
                            <td class="detail-value">{position_title}</td>
                        </tr>
                        <tr>
                            <td>Company</td>
                            <td class="detail-value">{company_name}</td>
                        </tr>
                        <tr>
                            <td>Salary</td>
                            <td class="detail-value">{formatted_salary} / year</td>
                        </tr>
                        <tr>
                            <td>Hourly Basis</td>
                            <td class="detail-value">{'Yes' if 'contract' in employment_type.lower() or 'hourly' in employment_type.lower() else 'No'}</td>
                        </tr>
                        <tr>
                            <td>Joining Date</td>
                            <td class="detail-value">{start_date_display}</td>
                        </tr>
                        <tr>
                            <td>Related Job</td>
                            <td class="detail-value">{position_title}</td>
                        </tr>
                    </table>
                </div>

                <!-- Offer Description Box (Optional if terms are present) -->
                {f'''<div class="offer-desc-box">
                    <div class="offer-desc-title">Offer Description</div>
                    <div class="offer-desc-text">
                        {offer_terms}
                    </div>
                </div>''' if offer_terms else ''}

                <p class="email-text" style="font-size: 13.5px;">
                    Please review the full offer details on the platform. You can accept, negotiate, or decline the offer directly from your dashboard.
                </p>

                <!-- CTA -->
                <div class="btn-wrap">
                    <a href="{base_url}/candidate/dashboard?tab=offer-letters" class="cta-button">Review Offer</a>
                </div>

                <!-- Red Notice box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed.
                </div>

                <!-- Note box -->
                <div class="note-box">
                    This offer was sent through FLIT by {company_name}. If you have questions about the offer, you can message the employer directly through the platform.
                </div>

            </div><!-- /email-body -->
        </div><!-- /card -->

        <!-- Footer -->
        <div class="email-footer">
            <p class="footer-support">
                Need help? <a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT &middot; Where talent meets opportunity</p>
        </div>
    </div>
</body>
</html>
"""

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@flit.com')

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content.strip(),
            from_email=from_email,
            to=[candidate_email]
        )

        # Attach the HTML version
        msg.attach_alternative(html_content, "text/html")

        # Attach the PDF offer letter
        if pdf_bytes:
            safe_filename = f"Offer_Letter_{position_title.replace(' ', '_')}_{company_name.replace(' ', '_')}.pdf"
            msg.attach(safe_filename, pdf_bytes, 'application/pdf')
            logger.info(
                f"PDF attachment added: {safe_filename} ({len(pdf_bytes)} bytes)"
            )
        else:
            logger.warning("No PDF bytes provided — email sent without attachment")

        # Send the email
        msg.send()

        logger.info(
            f"Offer letter email sent to {candidate_email} "
            f"for position: {position_title} at {company_name}"
        )
        return True

    except Exception as e:
        logger.error(f"Error sending offer letter email to {candidate_email}: {str(e)}")
        return False


def send_offer_response_email(employer_user, candidate_name, position_title,
                              company_name, action, salary=None, start_date=None, is_hourly=False, hourly_rate=None):
    """
    Send email to employer when a candidate accepts or declines their offer.

    Args:
        employer_user: The employer User instance
        candidate_name: Name of the candidate
        position_title: The position/offer title
        company_name: Company name
        action: 'accept' or 'decline'

    Returns:
        bool: True if email sent successfully
    """
    employer_email = employer_user.email
    employer_name = employer_user.get_full_name() or employer_user.email
    base_url = get_base_url()
    flit_logo_url = get_logo_url()
    ribbon_icon_url = f"{base_url}/frame.png"
    support_url = f"{base_url}/support"
    dashboard_url = f"{base_url}/employer/dashboard?tab=hired-candidates"
    
    is_accepted = action == 'accept'
    
    # Format salary display
    salary_display = "N/A"
    if is_hourly and hourly_rate:
        salary_display = f"${float(hourly_rate):,.2f} / hr"
    elif salary:
        salary_display = f"${float(salary):,.0f} / year"

    # Format start date
    start_date_display = start_date.strftime("%B %d, %Y") if start_date else "To be determined"

    if is_accepted:
        subject = f"🎉 Great News! {candidate_name} has accepted your offer — {position_title}"
        heading = f"{candidate_name} Accepted The Offer!"
        status_label = "OFFER ACCEPTED"
        badge_bg = "#e8faed"
        badge_color = "#27ae60"
        status_badge_bg = "#e6fffa"
        status_badge_text = "#319795"
        status_text = "ACCEPTED"
        message_intro = f"Great news! {candidate_name} has accepted the offer for the {position_title} position. Onboarding documents have been automatically triggered."
        badge_icon_url = ribbon_icon_url
    else:
        subject = f"{candidate_name} has declined your offer — {position_title}"
        heading = f"{candidate_name} Has Declined The Offer"
        status_label = "OFFER DECLINED"
        badge_bg = "#fff5f5"
        badge_color = "#e53e3e"
        status_badge_bg = "#fff5f5"
        status_badge_text = "#e53e3e"
        status_text = "DECLINED"
        message_intro = f"We're writing to inform you that {candidate_name} has declined the offer for the {position_title} position."
        badge_icon_url = f"{base_url}/reject.png"

    text_content = f"""
Hello {employer_name},

{message_intro}

OFFER DETAILS:
Candidate: {candidate_name}
Role: {position_title}
Salary: {salary_display}
Start Date: {start_date_display}
Status: {status_text}

Best regards,
FLIT Platform
"""

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #dce8f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #1e3a7b;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        .email-header {{
            text-align: left;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: flex-start;
        }}

        .logo-img {{
            height: 36px;
            width: auto;
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}

        .badge-icon {{
            width: 42px;
            height: 42px;
            background-color: {badge_bg};
            border-radius: 50%;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
            text-align: center;
        }}

        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: {badge_color};
            text-transform: uppercase;
            margin-left: 8px;
            display: inline-block;
            vertical-align: middle;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 16px;
            line-height: 28.8px;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #3d3d5c;
            margin-bottom: 24px;
            text-align: center;
        }}

        .detail-box {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
        }}

        .detail-box-title {{
            font-size: 11px;
            font-weight: 700;
            color: #7a7a99;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}

        .detail-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .detail-table td {{
            padding: 14px 0;
            border-bottom: 1px solid #eef0f5;
            font-size: 14px;
            color: #7a7a99;
        }}

        .detail-table tr:last-child td {{
            border-bottom: none;
            padding-bottom: 0;
        }}

        .detail-value {{
            text-align: right;
            color: #14181f !important;
            font-weight: 600;
        }}

        .status-badge {{
            background-color: {status_badge_bg};
            color: {status_badge_text};
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
        }}

        .btn-wrap {{
            text-align: center;
            margin-bottom: 24px;
            margin-top: 24px;
        }}

        .cta-button {{
            display: inline-block;
            background-color: #1e3a7b;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 40px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        .dashboard-tip {{
            background-color: #f7fafc;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
            color: #718096;
            font-size: 14px;
            border: 1px solid #edf2f7;
            margin-top: 24px;
        }}

        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
            background-color: #dce8f5;
        }}

        .footer-support {{
            font-size: 13px;
            color: #3d3d5c;
            margin-bottom: 6px;
        }}

        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}

        .footer-copy {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 4px;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header, .email-body, .email-footer {{ padding-left: 20px; padding-right: 20px; }}
            .email-heading {{ font-size: 22px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <div class="email-header">
                <img src="{flit_logo_url}" alt="FLIT" class="logo-img">
            </div>
            
            <div class="email-body">
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{badge_icon_url}" alt="" width="24" height="24" style="display:inline-block; vertical-align:middle;">
                    </div>
                    <span class="badge-label">{status_label}</span>
                </div>

                <h1 class="email-heading">{heading}</h1>
                <p class="email-text">{message_intro}</p>

                <div class="detail-box">
                    <div class="detail-box-title">OFFER DETAILS</div>
                    <table class="detail-table">
                        <tr>
                            <td>Candidate</td>
                            <td class="detail-value">{candidate_name}</td>
                        </tr>
                        <tr>
                            <td>Role</td>
                            <td class="detail-value">{position_title}</td>
                        </tr>
                        <tr>
                            <td>Salary</td>
                            <td class="detail-value">{salary_display}</td>
                        </tr>
                        <tr>
                            <td>Start Date</td>
                            <td class="detail-value">{start_date_display}</td>
                        </tr>
                        <tr>
                            <td>Status</td>
                            <td class="detail-value"><span class="status-badge">{status_text}</span></td>
                        </tr>
                    </table>
                </div>

                {f'''<div class="btn-wrap">
                    <a href="{dashboard_url}" class="cta-button">Start Onboarding</a>
                </div>''' if is_accepted else ''}

                <div class="dashboard-tip">
                    You can track progress from your dashboard.
                </div>
            </div>
        </div>

        <div class="email-footer">
            <p class="footer-support">
                Need help? <a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">
                © 2026 FLIT · Where talent meets opportunity
            </p>
        </div>
    </div>
</body>
</html>
"""

    return send_email(employer_email, subject, text_content, html_content)



def send_password_reset_email(user, reset_url):
    """
    Send password reset email with a clean, professional styled template
    matching the FLIT brand design guidelines.
    
    Args:
        user: User model instance
        reset_url: The password reset URL with token
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    user_name = user.first_name or user.username
    user_email = user.email
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"

    # Truncate long token URL for display only (keep full URL in href)
    display_url = reset_url if len(reset_url) <= 55 else reset_url[:52] + "..."

    # Frame icon URL from frontend public folder (placeholder)
    frame_icon_url = f"{base_url}/security.png"

    subject = 'Reset your FLIT password'

    # Plain text fallback
    text_content = f"""
Hello {user_name},

We received a request to reset the password for your FLIT account.
Click the button below to choose a new password.

{reset_url}

This link expires in 10 minutes. If you didn't create an account on FLIT,
you can safely ignore this email.

Need help? Contact Support: {support_url}

© 2026 FLIT · Where talent meets opportunity
This is an automated message. Please do not reply directly.
"""

    # HTML version — pixel-perfect match to the new design
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #dce8f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        /* ── Outer wrapper ─────────────────────────────── */
        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        /* ── Card ──────────────────────────────────────── */
        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #1e3a7b; /* Bold top border only */
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        /* ── Header (logo row) ─────────────────────────── */
        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        /* ── Body ──────────────────────────────────────── */
        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        /* badge row */
        .badge-row {{
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 18px;
            gap: 10px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #fff4e5;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #f39c12;
            text-transform: uppercase;
        }}

        /* heading */
        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 16px;
            line-height: 28.8px;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        /* body text */
        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #3d3d5c;
            margin-bottom: 28px;
            text-align: center;
        }}

        /* CTA button */
        .btn-wrap {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #1e3a7b;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 40px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        /* fallback link */
        .fallback-text {{
            font-size: 12.5px;
            color: #7a7a99;
            margin-bottom: 24px;
            line-height: 1.6;
            text-align: center;
        }}
        .fallback-text a {{
            color: #1e3a7b;
            word-break: break-all;
        }}

        /* notice box */
        .notice-box {{
            background-color: #f5f6fa;
            border-radius: 8px;
            padding: 14px 18px;
            font-size: 13px;
            color: #4a4a6a;
            line-height: 1.6;
            display: flex;
            gap: 10px;
            align-items: flex-start;
        }}
        .notice-icon {{
            font-size: 15px;
            flex-shrink: 0;
            margin-top: 1px;
        }}

        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #b91c1c;
            line-height: 1.6;
            text-align: center;
            margin-top: 16px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #8b0000;
        }}

        /* ── Footer ────────────────────────────────────── */
        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
        }}
        .footer-support {{
            font-size: 13.5px;
            color: #3d3d5c;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 4px;
        }}
        .footer-auto {{
            font-size: 11px;
            color: #b0b0c8;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
            .email-heading {{ font-size: 22px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">

            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{frame_icon_url}" alt="Security" width="24" height="24" style="display:inline-block; vertical-align:middle;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none; font-size: 18px;">🔑</span>
                    </div>
                    <span class="badge-label">SECURITY</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">Reset Your Password</h1>

                <!-- Body copy -->
                <p class="email-text">
                    We received a request to reset the password for your FLIT account.<br/>
                    Click the button below to choose a new password.
                </p>

                <!-- CTA -->
                <div class="btn-wrap">
                    <a href="{reset_url}" class="cta-button">Reset Password</a>
                </div>

                <!-- Notice box -->
                <div class="notice-box">
                    <span class="notice-icon">&#128274;</span>
                    <span>
                        This link expires in 24 hours. If you didn't create an account on FLIT,
                        you can safely ignore this email.
                    </span>
                </div>

            </div><!-- /email-body -->

            <!-- Footer -->
            <div class="email-footer">
                <p class="footer-support">
                    Need help?&nbsp;<a href="{support_url}">Contact Support</a>
                </p>
                <p class="footer-copy">© 2026 FLIT &middot; Where talent meets opportunity</p>
                <p class="footer-auto">This is an automated message. Please do not reply directly.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    return send_email(user_email, subject, text_content, html_content)


def send_reference_request_email(reference_email, candidate_name, relationship, company_name, accept_url, deny_url):
    """
    Send an email to a professional reference requesting them to fill out a reference form for a candidate.
    """
    subject = f"Reference Request for {candidate_name}"
    logo_url = get_logo_url()
    base_url = get_base_url()
    support_url = f"{base_url}/support"
    
    # User icon for reference
    frame_icon_url = f"{base_url}/user.png"
    
    candidate_first_name = candidate_name.split()[0] if candidate_name else 'Candidate'
    
    # Plain text version
    text_content = f"""
Hello,

{candidate_name} has listed you as a professional reference on FLIT, a hiring platform for modern talent. They've invited you to share your perspective on their professional capabilities.

REQUEST DETAILS:
Candidate: {candidate_name}
Relationship: {relationship}
Company: {company_name}
You can respond to this request by clicking one of the links below:

Accept Reference: {accept_url}
Decline Reference: {deny_url}

Your response is confidential and will only be shared with the hiring team.
This link is secure and time-sensitive. If you believe this was sent in error or do not wish to provide a reference, you may disregard this email.

Need help? Contact Support: {support_url}
© 2026 FLIT · Where talent meets opportunity
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #dce8f5;
            font-family: 'Inter', Arial, sans-serif;
            color: #1a1a2e;
            padding: 32px 16px;
        }}

        .wrapper {{
            max-width: 560px;
            margin: 0 auto;
            font-family: 'Inter', Arial, sans-serif;
        }}

        .card {{
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            border: none;
            border-top: 4px solid #1e3a7b;
            box-shadow: 0 4px 24px rgba(30, 58, 123, 0.10);
        }}

        .email-header {{
            text-align: center;
            padding: 20px 36px;
            border-bottom: 1px solid #eef0f5;
            background-color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-img {{
            height: 36px;
            width: auto;
            
        }}

        .email-body {{
            padding: 36px 36px 28px 36px;
        }}

        .badge-row {{
            text-align: center;
            margin-bottom: 18px;
        }}
        .badge-icon {{
            width: 42px;
            text-align: center;
            height: 42px;
            background-color: #f5eeff;
            border-radius: 50%;
            display: inline-block;
            vertical-align: middle;
            line-height: 42px;
        }}
        .badge-icon img {{
            display: inline-block;
            vertical-align: middle;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #8b5cf6;
            text-transform: uppercase;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }}

        .email-heading {{
            font-size: 24px;
            font-weight: 700;
            color: #14181f;
            margin-bottom: 16px;
            line-height: 28.8px;
            letter-spacing: -0.72px;
            text-align: center;
        }}

        .email-text {{
            font-size: 15px;
            line-height: 1.7;
            color: #3d3d5c;
            margin-bottom: 24px;
        }}

        .detail-box {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 24px;
        }}
        .detail-box-title {{
            font-size: 11px;
            font-weight: 700;
            color: #7a7a99;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .detail-table td {{
            padding: 14px 0;
            border-bottom: 1px solid #eef0f5;
            font-size: 14px;
            color: #7a7a99;
        }}
        .detail-table tr:last-child td {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .detail-value {{
            text-align: right;
            color: #14181f !important;
            font-weight: 600;
        }}

        .form-disclaimer {{
            font-size: 13px;
            color: #7a7a99;
            margin-top: 16px;
            text-align: center;
        }}

        .btn-wrap-double {{
            text-align: center;
            margin-bottom: 24px;
            margin-top: 36px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #1e3a7b;
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 50px;
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 0.2px;
            margin: 0 8px;
        }}
        .cta-button-danger {{
            background-color: #ffffff;
            color: #c81e1e !important;
            border: 1px solid #c81e1e;
        }}

        .notice-box {{
            background-color: #fbfbfd;
            border: 1px solid #eef0f5;
            border-radius: 8px;
            padding: 18px;
            font-size: 12px;
            color: #7a7a99;
            line-height: 1.6;
            margin-bottom: 24px;
        }}

        .red-notice-box {{
            background-color: #fce8e8;
            border: 1px solid #c81e1e;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            color: #b91c1c;
            line-height: 1.6;
            text-align: center;
            margin-top: 16px;
        }}
        .red-notice-box strong {{
            display: block;
            margin-bottom: 4px;
            font-size: 14px;
            color: #8b0000;
        }}
        
        .email-footer {{
            padding: 20px 36px 28px 36px;
            text-align: center;
            background-color: #dce8f5;
        }}
        .footer-support {{
            font-size: 13px;
            color: #3d3d5c;
            margin-bottom: 6px;
        }}
        .footer-support a {{
            color: #1e3a7b;
            font-weight: 600;
            text-decoration: none;
        }}
        .footer-copy {{
            font-size: 12px;
            color: #9494b0;
            margin-bottom: 4px;
        }}
        .footer-auto {{
            font-size: 11px;
            color: #b0b0c8;
        }}

        @media only screen and (max-width: 600px) {{
            .email-header,
            .email-body,
            .email-footer {{ padding-left: 20px; padding-right: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="FLIT logo" class="logo-img" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{frame_icon_url}" alt="Reference Request" width="24" height="24" style="display:inline-block; vertical-align:middle;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
                        <span style="display:none; font-size: 20px; color: #8b5cf6;">&#128100;</span>
                    </div>
                    <span class="badge-label">REFERENCE REQUEST</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">Reference Request</h1>

                <!-- Body copy -->
                <p class="email-text">
                    <span style="font-weight: 700; color: #1e3a7b;">{candidate_name}</span> has listed you as a professional reference on FLIT, a hiring platform for modern talent. They've invited you to share your perspective on their professional capabilities.
                </p>

                <!-- Detail Box -->
                <div class="detail-box">
                    <div class="detail-box-title">REQUEST DETAILS</div>
                    <table class="detail-table">
                        <tr>
                            <td>Candidate</td>
                            <td class="detail-value">{candidate_name}</td>
                        </tr>
                        <tr>
                            <td>Relationship</td>
                            <td class="detail-value">{relationship}</td>
                        </tr>
                        <tr>
                            <td>Company</td>
                            <td class="detail-value">{company_name}</td>
                        </tr>
                    </table>
                </div>

                <!-- Action Buttons -->
                <div class="btn-wrap-double">
                    <a href="{accept_url}" class="cta-button">Accept Reference</a>
                    <a href="{deny_url}" class="cta-button cta-button-danger">Decline Reference</a>
                </div>

                <div class="form-disclaimer">
                    Your response is confidential and will only be shared with the hiring team.
                </div>

                <!-- Red Notice Box -->
                <div class="red-notice-box">
                    <strong>PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed
                </div>

            </div><!-- /email-body -->

        </div>
        
        <div class="email-footer">
            <p class="footer-support">
                Need help?&nbsp;<a href="{support_url}">Contact Support</a>
            </p>
            <p class="footer-copy">© 2026 FLIT &middot; Where talent meets opportunity</p>
            <p class="footer-auto">This is an automated message. Please do not reply directly.</p>
        </div>
    </div>
</body>
</html>
"""

    return send_email(reference_email, subject, text_content, html_content)
