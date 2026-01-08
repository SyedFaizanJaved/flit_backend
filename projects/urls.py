from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProjectViewSet, PublicProjectViewSet

router = DefaultRouter()
router.register(r'', ProjectViewSet, basename='project')  # Sirf ek registration

public_list = PublicProjectViewSet.as_view({'get': 'list'})
public_detail = PublicProjectViewSet.as_view({'get': 'retrieve'})

urlpatterns = [
    path('', include(router.urls)),
    path('public/projects/', public_list, name='public-project-list'),
    path('public/projects/<int:pk>/', public_detail, name='public-project-detail'),
]