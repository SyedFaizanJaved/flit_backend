from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.EmployerViewSet, basename='employers')

urlpatterns = [
    # Registration
    path('register/', views.EmployerRegistrationView.as_view(), name='employer-register'),
    path('', include(router.urls)),
]
