import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.utils import timezone
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from .models import ReferenceRequest
from .serializers import ReferenceRequestSerializer
from uuid import UUID

logger = logging.getLogger(__name__)


class ReferenceResponsesView(APIView):
    """
    Get all reference responses for the authenticated candidate
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        # Get all reference requests for the current user's candidate profile
        reference_requests = ReferenceRequest.objects.filter(
            candidate=request.user.candidate_profile,
            status__in=['accepted', 'declined', 'completed'] 
        ).order_by('-updated_at')
        
        serializer = ReferenceRequestSerializer(reference_requests, many=True)
        return Response(serializer.data)
    

class VerifyReferenceTokenView(APIView):
    """
    Verify if a reference token is valid and get reference request details
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, *args, **kwargs):
        token = request.query_params.get('token')
        
        if not token:
            return Response(
                {'status': 'error', 'message': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # First check if token is in valid UUID format
            try:
           
                UUID(token)
            except ValueError:
                return Response(
                    {'status': 'error', 'message': 'Invalid token format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            ref_request = ReferenceRequest.objects.get(
                token=token,
                status='pending',
                expires_at__gt=timezone.now()
            )
            
            return Response({
                'status': 'success',
                'message': 'Token is valid',
                'data': ReferenceRequestSerializer(ref_request).data
            })
            
        except ReferenceRequest.DoesNotExist:
            logger.warning(f'Invalid or expired token attempt: {token}')
            return Response(
                {
                    'status': 'error',
                    'message': 'Invalid or expired token',
                    'code': 'invalid_token'
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            logger.error(f'Error verifying token {token}: {str(e)}', exc_info=True)
            return Response(
                {
                    'status': 'error',
                    'message': 'An error occurred while verifying the token',
                    'code': 'server_error'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReferenceResponseView(APIView):
    """
    Handle reference responses (accept/deny) and view reference request details
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, *args, **kwargs):
        """
        GET request to view reference request details using token
        """
        token = request.query_params.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            ref_request = ReferenceRequest.objects.get(
                token=token,
                expires_at__gt=timezone.now()
            )
            
            return Response({
                'status': 'success',
                'reference_request': ReferenceRequestSerializer(ref_request).data
            })
            
        except ReferenceRequest.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired token'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        action = request.data.get('action')
        
        if not token or action not in ['accept', 'deny']:
            return Response(
                {'error': 'Token and valid action (accept/deny) are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # First check if token exists and is not expired
            ref_request = ReferenceRequest.objects.get(
                token=token,
                expires_at__gt=timezone.now()
            )
            
            # Check if the reference request can be updated
            if ref_request.status not in ['pending', 'accepted']:
                return Response(
                    {'error': f'This reference request has already been {ref_request.get_status_display().lower()}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update status based on action
            new_status = 'accepted' if action == 'accept' else 'declined'
            
            # Only update if status is changing
            if ref_request.status != new_status:
                ref_request.status = new_status
                
                # Save reply message if provided and request is being accepted
                if action == 'accept' and 'reply_message' in request.data:
                    ref_request.reply_message = request.data['reply_message']
                
                ref_request.save()
                
                # TODO: Send notification to candidate about the response
                
                return Response({
                    'status': 'success',
                    'message': f'Reference request has been {new_status}',
                    'reference_request': ReferenceRequestSerializer(ref_request).data
                })
            else:
                return Response({
                    'status': 'success',
                    'message': f'Reference request is already {ref_request.get_status_display().lower()}',
                    'reference_request': ReferenceRequestSerializer(ref_request).data
                })
            
        except ReferenceRequest.DoesNotExist:
            try:
                # Check if token exists but is expired
                ReferenceRequest.objects.get(token=token)
                return Response(
                    {'error': 'This reference link has expired'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            except ReferenceRequest.DoesNotExist:
                return Response(
                    {'error': 'Invalid reference token'}, 
                    status=status.HTTP_404_NOT_FOUND
                )


def send_reference_request_email(ref_request, request):
    """
    Send reference request email with accept/deny buttons
    """
    try:
        frontend_url = getattr(settings, 'FLIT_REQUEST_URL/reference-response')
        backend_url = request.build_absolute_uri('/')[:-1]  # Get current backend URL
        
        logo_url = f"{getattr(settings, 'FLIT_REQUEST_URL', 'https://dev.flit.works')}/flit_icon.png"  # Get logo URL from FLIT_REQUEST_URL
        
        accept_url = f"{frontend_url}?&token={ref_request.token}&action=accept"
        deny_url = f"{frontend_url}?&token={ref_request.token}&action=deny"  
        
        subject = f"Reference Request from {ref_request.candidate.full_name}"
        
        # Plain text version for email clients that don't support HTML
        text_content = f"""
        Hello {ref_request.reference_name},
        
        {ref_request.candidate.full_name} has requested you as a reference.
        
        Message from {ref_request.candidate.full_name.split()[0]}:
        {ref_request.request_message or 'No message provided.'}
        
        You can respond to this request by clicking one of the links below:
        
        Accept: {accept_url}
        Deny: {deny_url}
        
        This link will expire on {ref_request.expires_at.strftime('%B %d, %Y')}.
        
        Thank you,
        The {getattr(settings, 'SITE_NAME', 'Flit')} Team
        """
        
        # HTML version with eye-catching design and logo
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reference Request - Flit</title>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    font-family: 'Arial', sans-serif;
                    line-height: 1.6;
                    color: #333333;
                    background-color: #f4f7fa;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
                    border: 2px solid #e0e6ed;
                }}
                .header {{
                    background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);
                    padding: 30px;
                    text-align: center;
                    color: white;
                    position: relative;
                    border-bottom: 2px solid #e0e6ed;
                }}
                .logo {{
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 10px;
                }}
                .logo img {{
                    height: 40px;
                    width: auto;
                    margin-right: 10px;
                }}
                .logo-text {{
                    font-family: 'Montserrat', 'Arial', sans-serif;
                    font-size: 28px;
                    font-weight: 700;
                    letter-spacing: 0.05em;
                    color: white;
                    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }}
                .header-title {{
                    font-size: 24px;
                    margin: 0;
                    font-weight: 600;
                    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
                }}
                .content {{
                    background-color: #ffffff;
                    padding: 40px;
                    border: 1px solid #e0e6ed;
                    border-top: none;
                    border-bottom: none;
                }}
                .greeting {{
                    font-size: 18px;
                    color: #2c3e50;
                    margin-bottom: 10px;
                }}
                .request-info {{
                    background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 5px solid #3498db;
                    border: 1px solid #e0e6ed;
                }}
                .request-info h3 {{
                    margin: 0 0 10px 0;
                    color: #2c3e50;
                    font-size: 16px;
                }}
                .request-info p {{
                    margin: 0;
                    color: #555;
                }}
                .message {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #3498db;
                    font-style: italic;
                    border: 1px solid #e0e6ed;
                }}
                .button-container {{
                    margin: 40px 100px;
                    text-align: center;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 20px;
                    flex-wrap: wrap;
                }}
                .button {{
                    display: inline-block;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 50px;
                    font-weight: bold;
                    color: white !important;
                    text-align: center;
                    cursor: pointer;
                    font-size: 12px;
                    transition: transform 0.2s ease, box-shadow 0.2s ease;
                    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    text-decoration: none !important;
                }}
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
                }}
                .button-accept {{
                    background: linear-gradient(135deg, #2ecc71 0%, #27ae60 100%);
                    color: white !important;
                    white-space: nowrap;
                    padding: 10px 20px;

                }}
                .button-deny {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white !important;
                    margin-left: 20px;
                    white-space: nowrap;
                    padding: 10px 20px;

                }}
                .expiry-note {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    color: #856404;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                    font-style: italic;
                    margin: 20px 0;
                }}
                .footer {{
                    background-color: #34495e;
                    color: white;
                    padding: 25px;
                    text-align: center;
                    font-size: 14px;
                    border-top: 2px solid #e0e6ed;
                }}
                .footer p {{
                    margin: 0;
                }}
                @media only screen and (max-width: 600px) {{
                    .container {{ border-radius: 0; }}
                    .content {{ padding: 20px; }}
                    .button-container {{ flex-direction: column; gap: 20px; }}
                    .button {{ width: 100%; max-width: 250px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">
                        <img src="{logo_url}" alt="Flit Logo - Realistic Hummingbird" style="display: block;" />
                        <span class="logo-text">FLIT</span>
                    </div>
                    <h1 class="header-title">Reference Request</h1>
                </div>
                
                <div class="content">
                    <p class="greeting">Hello {ref_request.reference_name},</p>
                    
                    <p>{ref_request.candidate.full_name} has requested you as a reference for their exciting journey ahead!</p>
                    
                    <div class="request-info">
                        <h3>🌟 Quick Details</h3>
                        <p><strong>Candidate:</strong> {ref_request.candidate.full_name}</p>
                        <p><strong>Requested on:</strong> {ref_request.created_at.strftime('%B %d, %Y')}</p>
                    </div>
                    
                    <div class="message">
                        <p><strong>Personal Message from {ref_request.candidate.full_name.split()[0]}:</strong></p>
                        <p>{ref_request.request_message or 'No message provided – but your insight would mean the world!'}</p>
                    </div>
                    
                    <p>Your response helps {ref_request.candidate.full_name.split()[0]} soar to new heights. Please let us know your decision:</p>
                    
                    <div class="button-container">
                        <a href="{accept_url}" class="button button-accept">Accept Reference</a>
                        <a href="{deny_url}" class="button button-deny">Decline Reference</a>
                    </div>
                    
                </div>
                
                <div class="footer">
                    <p>Thank you for being an amazing supporter!<br>
                    The <strong>Flit</strong> Team<br>
                    <small>Empowering careers, one reference at a time.</small></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content.strip(),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@flit.com'),
            to=[ref_request.reference_email]
        )
        
        # Attach the HTML version
        msg.attach_alternative(html_content, "text/html")
        
        # Send the email
        msg.send()
        
        return True
        
    except Exception as e:
        logger.error(f"Error sending reference request email: {str(e)}")
        return False