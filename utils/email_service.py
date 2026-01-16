"""
Email service module for sending professional email notifications
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def get_base_url():
    """Get the base frontend URL from settings"""
    return getattr(settings, 'FLIT_REQUEST_URL', 'http://localhost:3000')


def get_logo_url():
    """Get the logo URL for email templates"""
    base_url = get_base_url()
    return f"{base_url}/flit_icon.png"


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
            color: white;
            padding: 25px;
            text-align: center;
            font-size: 14px;
            border-top: 2px solid #e0e6ed;
        }
        .footer p {
            margin: 0;
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
            to=[to_email]
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
