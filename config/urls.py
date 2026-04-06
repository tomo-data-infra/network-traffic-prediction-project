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
from calendar_api.views import EventSessionViewSet # Import your View

# 1. Create a router and register our viewset with it.
router = DefaultRouter()
router.register(r'event_sessions', EventSessionViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    # 2. Include the router URLs under an 'api/' prefix
    path('api/', include(router.urls)),
]

