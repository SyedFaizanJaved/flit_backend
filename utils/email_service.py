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
            margin-right: 10px;
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


def send_shortlist_notification(candidate, job_or_project_title, application_type='job'):
    """
    Send email notification when a candidate is shortlisted
    
    Args:
        candidate: Candidate model instance
        job_or_project_title: Title of the job or project
        application_type: 'job' or 'project'
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    styles = get_email_styles()
    
    application_type_label = 'Job' if application_type == 'job' else 'Project'
    
    subject = f"Congratulations! You've been shortlisted for {job_or_project_title}"
    
    # Plain text version
    text_content = f"""
Hello {candidate_name},

Great news! You've been shortlisted for the {application_type_label.lower()} position: {job_or_project_title}

This is an exciting step forward in your application process. The employer has reviewed your profile and is interested in moving forward with you.

What's next?
- Keep an eye on your email for further communication from the employer
- You may be contacted for an interview or additional information
- Continue to showcase your skills and enthusiasm

We're rooting for you!

Best regards,
The {getattr(settings, 'SITE_NAME', 'Flit')} Team
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shortlisted - Flit</title>
    <style>
        {styles}
        .success-box {{
            background: linear-gradient(135deg, #2ecc71 0%, #27ae60 100%);
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            color: white;
            text-align: center;
        }}
        .success-box h2 {{
            margin: 0 0 10px 0;
            color: white;
            font-size: 24px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="{logo_url}" alt="Flit Logo" style="display: block;" />
                <span class="logo-text">FLIT</span>
            </div>
            <h1 class="header-title">Application Update</h1>
        </div>
        
        <div class="content">
            <p class="greeting">Hello {candidate_name},</p>
            
            <div class="success-box">
                <h2>🎉 Congratulations!</h2>
                <p style="margin: 0; font-size: 16px;">You've been shortlisted!</p>
            </div>
            
            <p>Great news! You've been shortlisted for the <strong>{application_type_label}</strong> position:</p>
            
            <div class="info-box">
                <h3>📋 Application Details</h3>
                <p><strong>{application_type_label}:</strong> {job_or_project_title}</p>
            </div>
            
            <p>This is an exciting step forward in your application process. The employer has reviewed your profile and is interested in moving forward with you.</p>
            
            <div class="message">
                <p><strong>What's next?</strong></p>
                <ul style="margin: 10px 0; padding-left: 20px;">
                    <li>Keep an eye on your email for further communication from the employer</li>
                    <li>You may be contacted for an interview or additional information</li>
                    <li>Continue to showcase your skills and enthusiasm</li>
                </ul>
            </div>
            
            <p>We're rooting for you! Best of luck with the next steps.</p>
            
            <div class="no-reply-box">
                <strong>🚫 PLEASE DO NOT REPLY TO THIS EMAIL</strong>
                This is an automated message sent from an unmonitored mailbox. 
                Replies to this email will not be received or reviewed.
            </div>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            The <strong>Flit</strong> Team<br>
            <small>Empowering careers, one opportunity at a time.</small></p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(candidate_email, subject, text_content, html_content)


def send_rejection_notification(candidate, job_or_project_title, application_type='job', rejection_reason=None):
    """
    Send email notification when a candidate is rejected
    
    Args:
        candidate: Candidate model instance
        job_or_project_title: Title of the job or project
        application_type: 'job' or 'project'
        rejection_reason: Optional rejection reason message
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    styles = get_email_styles()
    
    application_type_label = 'Job' if application_type == 'job' else 'Project'
    
    subject = f"Update on your application for {job_or_project_title}"
    
    # Plain text version
    text_content = f"""
Hello {candidate_name},

Thank you for your interest in the {application_type_label.lower()} position: {job_or_project_title}

After careful consideration, we've decided to move forward with other candidates whose qualifications more closely match our current needs.

{f'Reason: {rejection_reason}' if rejection_reason else ''}

This decision was not easy, and we appreciate the time and effort you put into your application. We encourage you to keep applying to other opportunities that align with your skills and interests.

We wish you the best in your job search and future endeavors.

Best regards,
The {getattr(settings, 'SITE_NAME', 'Flit')} Team
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Application Update - Flit</title>
    <style>
        {styles}
        .info-box-rejection {{
            background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 5px solid #f39c12;
            border: 1px solid #e0e6ed;
        }}
        .encouragement {{
            background-color: #e8f5e9;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #4caf50;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="{logo_url}" alt="Flit Logo" style="display: block;" />
                <span class="logo-text">FLIT</span>
            </div>
            <h1 class="header-title">Application Update</h1>
        </div>
        
        <div class="content">
            <p class="greeting">Hello {candidate_name},</p>
            
            <p>Thank you for your interest in the <strong>{application_type_label}</strong> position:</p>
            
            <div class="info-box">
                <h3>📋 Application Details</h3>
                <p><strong>{application_type_label}:</strong> {job_or_project_title}</p>
            </div>
            
            <p>After careful consideration, we've decided to move forward with other candidates whose qualifications more closely match our current needs.</p>
            
            {f'<div class="info-box-rejection"><p><strong>Note:</strong> {rejection_reason}</p></div>' if rejection_reason else ''}
            
            <div class="encouragement">
                <p><strong>💪 Keep Going!</strong></p>
                <p>This decision was not easy, and we appreciate the time and effort you put into your application. We encourage you to keep applying to other opportunities that align with your skills and interests.</p>
            </div>
            
            <p>We wish you the best in your job search and future endeavors.</p>
            {NO_REPLY_HTML}
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            The <strong>Flit</strong> Team<br>
            <small>Empowering careers, one opportunity at a time.</small></p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(candidate_email, subject, text_content, html_content)


def send_flit_pass_notification(candidate, employer_name, company_name=None):
    """
    Send email notification when an employer flits (likes/saves) a candidate profile
    
    Args:
        candidate: Candidate model instance
        employer_name: Name of the employer who flitted the profile
        company_name: Optional company name
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    candidate_name = candidate.full_name
    candidate_email = candidate.user.email
    logo_url = get_logo_url()
    styles = get_email_styles()
    
    company_info = f" from {company_name}" if company_name else ""
    
    subject = f"Your profile caught someone's attention! 🎯"
    
    # Plain text version
    text_content = f"""
Hello {candidate_name},

Exciting news! Your profile has been flitted (saved) by {employer_name}{company_info}.

This means an employer has shown interest in your profile and saved it for future opportunities. They may reach out to you when they have a position that matches your skills and experience.

Keep your profile updated and continue showcasing your best work. Opportunities are coming your way!

Best regards,
The {getattr(settings, 'SITE_NAME', 'Flit')} Team
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Profile Flitted - Flit</title>
    <style>
        {styles}
        .flit-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 25px;
            border-radius: 8px;
            margin: 20px 0;
            color: white;
            text-align: center;
        }}
        .flit-box h2 {{
            margin: 0 0 10px 0;
            color: white;
            font-size: 24px;
        }}
        .highlight-box {{
            background-color: #e3f2fd;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #2196f3;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="{logo_url}" alt="Flit Logo" style="display: block;" />
                <span class="logo-text">FLIT</span>
            </div>
            <h1 class="header-title">Profile Update</h1>
        </div>
        
        <div class="content">
            <p class="greeting">Hello {candidate_name},</p>
            
            <div class="flit-box">
                <h2>🎯 Your Profile Caught Attention!</h2>
                <p style="margin: 0; font-size: 16px;">Someone flitted your profile!</p>
            </div>
            
            <p>Exciting news! Your profile has been <strong>flitted</strong> (saved) by:</p>
            
            <div class="info-box">
                <h3>👤 Employer Details</h3>
                <p><strong>Name:</strong> {employer_name}</p>
                {f'<p><strong>Company:</strong> {company_name}</p>' if company_name else ''}
            </div>
            
            <div class="highlight-box">
                <p><strong>What does this mean?</strong></p>
                <p>An employer has shown interest in your profile and saved it for future opportunities. They may reach out to you when they have a position that matches your skills and experience.</p>
            </div>
            
            <div class="message">
                <p><strong>💡 Pro Tip:</strong> Keep your profile updated and continue showcasing your best work. Opportunities are coming your way!</p>
            </div>
            
            <p>Stay positive and keep applying. Your next opportunity might be just around the corner!</p>
            {NO_REPLY_HTML}
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            The <strong>Flit</strong> Team<br>
            <small>Empowering careers, one connection at a time.</small></p>
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
    recipient_name = recipient.first_name or recipient.username
    sender_name = sender.first_name or sender.username
    recipient_email = recipient.email
    
    logo_url = get_logo_url()
    styles = get_email_styles()
    base_url = get_base_url()
    
    # Construct chat URL (assuming /chat or /messages route)
    chat_url = f"{base_url}/candidate/dashboard"
    
    subject = f"New message from {sender_name}"
    
    # Plain text version
    text_content = f"""
Hello {recipient_name},

You have received a new message from {sender_name}:

"{message_content}"

Reply to this message here: {chat_url}

Best regards,
The {getattr(settings, 'SITE_NAME', 'Flit')} Team
"""
    
    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Message - Flit</title>
    <style>
        {styles}
        .message-box {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #6c5ce7;
            font-style: italic;
        }}
        .button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            padding: 12px 25px;
            border-radius: 25px;
            font-weight: bold;
            margin-top: 20px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="{logo_url}" alt="Flit Logo" style="display: block;" />
            </div>
            <h1 class="header-title">New Message</h1>
        </div>
        
        <div class="content">
            <p class="greeting">Hello {recipient_name},</p>
            
            <p>You have received a new message from <strong>{sender_name}</strong>:</p>
            
            <div class="message-box">
                "{message_content}"
            </div>
            
            <div style="text-align: center;">
                <a href="{chat_url}" class="button" style="color: white;">Reply Now</a>
            </div>
            {NO_REPLY_HTML}
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            The <strong>Flit</strong> Team<br>
            <small>Connecting you to your next opportunity.</small></p>
        </div>
    </div>
</body>
</html>
"""
    
    return send_email(recipient_email, subject, text_content, html_content)


def send_verification_email(user, verification_url):
    """
    Send email verification email with a clean, professional styled template
    matching the Flit brand design guidelines.
    
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

    subject = 'Verify your Flit email address'

    # Plain text fallback
    text_content = f"""
Hello {user_name},

Thanks for creating your profile on Flit, {user_name}.
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
            margin-right: 10px;
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
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 18px;
            gap: 10px;
        }}
        .badge-icon {{
            width: 42px;
            height: 42px;
            background-color: #eef2fb;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .badge-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #1e3a7b;
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
        <div class="card">

            <!-- Header -->
            <div class="email-header">
                <img src="{logo_url}" alt="Flit logo" class="logo-img" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{frame_icon_url}" alt="Account Verification" width="24" height="24" style="display:block;" />
                    </div>
                    <span class="badge-label">Account Verification</span>
                </div>

                <!-- Heading -->
                <h1 class="email-heading">Verify Your Email</h1>

                <!-- Body copy -->
                <p class="email-text">
                    Thanks for creating your profile on Flit,
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
                    This is an automated message sent from an unmonitored mailbox. Replies to this email will not be received or reviewed
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

        </div><!-- /card -->
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
(Powered by {getattr(settings, 'SITE_NAME', 'Flit')})
"""

    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Offer Letter - {company_name}</title>
    <style>
        {styles}
        .offer-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 25px;
            border-radius: 8px;
            margin: 20px 0;
            color: white;
            text-align: center;
        }}
        .offer-box h2 {{
            margin: 0 0 10px 0;
            color: white;
            font-size: 24px;
        }}
        .offer-box p {{
            margin: 0;
            font-size: 16px;
            color: rgba(255,255,255,0.9);
        }}
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .detail-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #ecf0f1;
            font-size: 14px;
        }}
        .detail-table td:first-child {{
            color: #7f8c8d;
            font-weight: bold;
            width: 40%;
        }}
        .detail-table td:last-child {{
            color: #2c3e50;
            font-weight: 600;
        }}
        .detail-table tr:last-child td {{
            border-bottom: 2px solid #667eea;
        }}
        .attachment-notice {{
            background-color: #e8f8f5;
            padding: 15px 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #1abc9c;
        }}
        .cta-box {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: center;
            border: 1px solid #e0e6ed;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="{logo_url}" alt="Flit Logo" style="display: block;" />
                <span class="logo-text">FLIT</span>
            </div>
            <h1 class="header-title">Offer Letter</h1>
        </div>

        <div class="content">
            <p class="greeting">Hello {candidate_name},</p>

            <div class="offer-box">
                <h2>🎉 Congratulations!</h2>
                <p>You've been offered a position!</p>
            </div>

            <p>We are thrilled to inform you that you have been selected for the following position at <strong>{company_name}</strong>:</p>

            <table class="detail-table">
                <tr>
                    <td>📋 Position</td>
                    <td>{position_title}</td>
                </tr>
                <tr>
                    <td>💼 Employment Type</td>
                    <td>{emp_type_display}</td>
                </tr>
                <tr>
                    <td>💰 Compensation</td>
                    <td>{formatted_salary}</td>
                </tr>
                <tr>
                    <td>📅 Start Date</td>
                    <td>{start_date_display}</td>
                </tr>
                <tr>
                    <td>📍 Location</td>
                    <td>{location or 'To be determined'}</td>
                </tr>
            </table>

            {f'<div class="info-box"><h3>📝 Additional Terms</h3><p>{offer_terms}</p></div>' if offer_terms else ''}

            <div class="attachment-notice">
                <p><strong>📎 Attachment:</strong> Your official offer letter is attached to this email as a PDF document. Please review it carefully.</p>
            </div>

            <div class="cta-box">
                <p><strong>Next Steps</strong></p>
                <p>Please review the attached offer letter and respond at your earliest convenience. If you have any questions, feel free to reach out to us.</p>
            </div>

            <p>We are excited about the possibility of you joining the <strong>{company_name}</strong> team and look forward to working with you!</p>
        </div>

        <div class="footer">
            <p>Best regards,<br>
            The <strong>{company_name}</strong> Team<br>
            <small>Powered by Flit — Empowering careers, one opportunity at a time.</small></p>
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
                              company_name, action):
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
    styles = get_email_styles()
    logo_url = get_logo_url()

    is_accepted = action == 'accept'

    if is_accepted:
        subject = f"🎉 Great News! {candidate_name} has accepted your offer — {position_title}"
        emoji = "🎉"
        heading = "Offer Accepted!"
        banner_color = "linear-gradient(135deg, #00b894 0%, #00cec9 100%)"
        status_text = "accepted"
        message_body = (
            f"<b>{candidate_name}</b> has <b style='color: #00b894;'>accepted</b> "
            f"your offer for the position of <b>{position_title}</b> at <b>{company_name}</b>."
        )
        next_steps = (
            "You can now proceed with the onboarding process. "
            "Please coordinate with the candidate to finalize the joining details."
        )
    else:
        subject = f"{candidate_name} has declined your offer — {position_title}"
        emoji = "📋"
        heading = "Offer Declined"
        banner_color = "linear-gradient(135deg, #636e72 0%, #b2bec3 100%)"
        status_text = "declined"
        message_body = (
            f"<b>{candidate_name}</b> has <b style='color: #d63031;'>declined</b> "
            f"your offer for the position of <b>{position_title}</b> at <b>{company_name}</b>."
        )
        next_steps = (
            "You may want to reach out to the candidate for feedback, "
            "or consider other candidates for this position."
        )

    text_content = f"""
Hello {employer_name},

{candidate_name} has {status_text} your offer for the position of {position_title} at {company_name}.

{'You can now proceed with the onboarding process.' if is_accepted else 'You may want to consider other candidates for this position.'}

Best regards,
Flit Platform
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        {styles}
        .status-banner {{
            background: {banner_color};
            padding: 25px;
            border-radius: 8px;
            margin: 20px 0;
            color: white;
            text-align: center;
        }}
        .status-banner h2 {{
            margin: 0 0 8px 0;
            color: white;
            font-size: 22px;
        }}
        .status-banner p {{
            margin: 0;
            font-size: 15px;
            color: rgba(255,255,255,0.9);
        }}
        .detail-card {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border: 1px solid #e0e6ed;
        }}
        .next-steps {{
            background-color: #e8f8f5;
            padding: 15px 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #00b894;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="{logo_url}" alt="Flit Logo" style="display: block;" />
                <span class="logo-text">FLIT</span>
            </div>
            <h1 class="header-title">Offer Response</h1>
        </div>

        <div class="content">
            <p class="greeting">Hello {employer_name},</p>

            <div class="status-banner">
                <h2>{emoji} {heading}</h2>
                <p>{candidate_name} has responded to your offer</p>
            </div>

            <p>{message_body}</p>

            <div class="detail-card">
                <p><strong>Position:</strong> {position_title}</p>
                <p><strong>Candidate:</strong> {candidate_name}</p>
                <p><strong>Status:</strong> {status_text.capitalize()}</p>
            </div>

            <div class="next-steps">
                <p><strong>Next Steps:</strong> {next_steps}</p>
            </div>
        </div>

        <div class="footer">
            <p>Best regards,<br>
            <strong>Flit Platform</strong><br>
            <small>Empowering careers, one opportunity at a time.</small></p>
        </div>
    </div>
</body>
</html>
"""

    return send_email(employer_email, subject, text_content, html_content)


def send_password_reset_email(user, reset_url):
    """
    Send password reset email with a clean, professional styled template
    matching the Flit brand design guidelines.
    
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

    subject = 'Reset your Flit password'

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
            margin-right: 10px;
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
                <img src="{logo_url}" alt="Flit logo" class="logo-img" />
            </div>

            <!-- Body -->
            <div class="email-body">

                <!-- Badge -->
                <div class="badge-row">
                    <div class="badge-icon">
                        <img src="{frame_icon_url}" alt="Security" width="24" height="24" style="display:block;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';" />
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
