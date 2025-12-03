import logging
import time
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('django.request')

class APILoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.start_time = time.time()
        return None

    def process_response(self, request, response):
        # Calculate request processing time
        total_time = time.time() - request.start_time
        
        # Log the request details
        log_data = {
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'processing_time': total_time,
            'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous',
            'query_params': dict(request.GET) if request.GET else {},
        }
        
        logger.info(
            "%s %s %s %s",
            request.method,
            request.path,
            response.status_code,
            f"{total_time:.2f}s"
        )
        
        return response
