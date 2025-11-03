from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JobViewSet, PublicJobViewSet

# Create a router for private routes
private_router = DefaultRouter()
private_router.register(r'', JobViewSet, basename='job')

# Register custom actions
private_router.register(r'my-jobs', JobViewSet, basename='my-jobs')

# Public endpoints
public_list = PublicJobViewSet.as_view({
    'get': 'list'
})
public_detail = PublicJobViewSet.as_view({
    'get': 'retrieve'
})

urlpatterns = [
    # Include the private router URLs
    path('', include(private_router.urls)),
    
    # Public endpoints
    path('public/jobs/', public_list, name='public-job-list'),
    path('public/jobs/<int:pk>/', public_detail, name='public-job-detail'),
]