"""
ASGI config for flit_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flit_backend.settings')

# Initialize Django
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()

# Import WebSocket URL patterns after Django is initialized
from chat.routing import websocket_urlpatterns

# Combine HTTP and WebSocket applications
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns
            )
        )
    )
})

# This variable is used by Daphne/ASGI servers
app = application
