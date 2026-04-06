import logging
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.utils import timezone
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from .models import ReferenceRequest
from .serializers import ReferenceRequestSerializer
from uuid import UUID
from utils.pagination import CustomPagination

logger = logging.getLogger(__name__)


class ReferenceResponsesView(generics.ListAPIView):
    """
    Get all reference responses for the authenticated candidate with pagination
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = ReferenceRequestSerializer
    
    def get_queryset(self):
        # Get all reference requests for the current user's candidate profile
        return ReferenceRequest.objects.filter(
            candidate=self.request.user.candidate_profile,
            status__in=['accepted', 'declined', 'completed']
        ).order_by('-updated_at')
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            
            # Get total counts for different statuses
            status_counts = {
                'total': queryset.count(),
                'accepted': queryset.filter(status='accepted').count(),
                'declined': queryset.filter(status='declined').count(),
                'completed': queryset.filter(status='completed').count(),
            }
            
            # Prepare response data
            response_data = {
                'reference_responses': serializer.data,
                'counts': status_counts
            }
            
            return self.get_paginated_response(response_data)
        
        # Fallback if pagination is not used
        serializer = self.get_serializer(queryset, many=True)
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
    Send reference request email utilizing the new Figma template from utils
    """
    from utils.email_service import send_reference_request_email as new_send_email
    
    try:
        base_url = getattr(settings, 'FLIT_REQUEST_URL')
        # The new design has 'Submit Reference' which acts as the main entry point
        reference_url = f"{base_url}/reference-response?token={ref_request.token}"
        
        relationship_display = ref_request.get_suggested_relationship_display() if ref_request.suggested_relationship else "Professional Contact"
        company_display = ref_request.suggested_company if ref_request.suggested_company else "None specified"
        
        # Call the new design function in utils/email_service.py
        email_sent = new_send_email(
            reference_email=ref_request.reference_email,
            candidate_name=ref_request.candidate.full_name,
            relationship=relationship_display,
            company_name=company_display,
            reference_url=reference_url
        )
        return email_sent
        
    except Exception as e:
        logger.error(f"Error sending reference request email: {str(e)}")
        return False