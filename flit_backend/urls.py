"""
URL configuration for flit_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

# Import WebSocket URL patterns
from chat.routing import websocket_urlpatterns


def welcome_root(request):
    return JsonResponse({
        "status": "ok",
        "message": "Welcome to FLIT APIs",
    })

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "message": "Backend is healthy",
    })

urlpatterns = [
    path('', welcome_root, name='root'),
    
    # Chat HTTP URLs
    path('chat/', include('chat.urls')),
    path('health', health_check, name='health'),
    path('admin/', admin.site.urls),
    
    # WebSocket URLs
    path('ws/', include(websocket_urlpatterns)),

    # API routes
    path('api/auth/', include('accounts.urls')),
    path('api/candidates/', include('candidates.urls')),
    path('api/applications/', include('applications.urls')),
    path('api/employers/', include('employers.urls')),
    path('api/companies/', include('companies.urls')),
    path('api/jobs/', include('jobs.urls')),
    path('api/projects/', include('projects.urls')),
    path('api/chat/', include('chat.urls')),
    path('api/vr-meet/', include('vr_meet.urls')),
    path('api/stories/', include('stories.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
