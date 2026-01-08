# jobs/urls.py (optimized – single router registration)
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JobViewSet, PublicJobViewSet

router = DefaultRouter()
router.register(r'', JobViewSet, basename='job')

# Public endpoints
public_list = PublicJobViewSet.as_view({'get': 'list'})
public_detail = PublicJobViewSet.as_view({'get': 'retrieve'})

urlpatterns = [
    path('', include(router.urls)),
    
    # Public endpoints
    path('public/jobs/', public_list, name='public-job-list'),
    path('public/jobs/<int:pk>/', public_detail, name='public-job-detail'),
]