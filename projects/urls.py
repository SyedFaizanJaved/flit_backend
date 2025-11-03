from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProjectViewSet, PublicProjectViewSet

# Router for private APIs
private_router = DefaultRouter()
# Register the main viewset
private_router.register(r'', ProjectViewSet, basename='project')
# Register custom actions
private_router.register(r'my-projects', ProjectViewSet, basename='my-projects')

# Public views
public_list = PublicProjectViewSet.as_view({'get': 'list'})
public_detail = PublicProjectViewSet.as_view({'get': 'retrieve'})

urlpatterns = [
    path('', include(private_router.urls)),
    
    # Public APIs
    path('public/projects/', public_list, name='public-project-list'),
    path('public/projects/<int:pk>/', public_detail, name='public-project-detail'),
]