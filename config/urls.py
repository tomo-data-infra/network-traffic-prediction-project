"""
URL configuration for config project.

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
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from calendar_api.views import EventSessionViewSet, PingLogViewSet, TargetViewSet, PingDataView, TrafficAgentView # Import your View

# 1. Create a router and register our viewset with it.
router = DefaultRouter()
router.register(r'event_sessions', EventSessionViewSet)
router.register(r'ping_logs', PingLogViewSet)
router.register(r'targets', TargetViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Group all API endpoints under 'api/'
    path('api/', include([
        # 1. Include the auto-generated ViewSet urls (EventSessions, etc.)
        path('', include(router.urls)),
        
        # 2. Add your custom ML Ping Data endpoint
        # React will now fetch this from: http://localhost:8000/api/ping_data/
        path('ping_data/', PingDataView.as_view(), name='ping_data'),
        path('traffic_agent/', TrafficAgentView.as_view(), name='traffic_agent'),
    ])),
]
