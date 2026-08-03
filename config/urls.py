"""URL configuration: REST API routes, ML endpoints, and the AI agent gateway."""

from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from calendar_api.views import (
    EventSessionViewSet, PingLogViewSet, TargetViewSet, TrainModelView, PingDataView,
    DatabaseMaintenanceView, NetOpsAgentCoreView, AdminLoginView,
)

router = DefaultRouter()
router.register(r'event_sessions', EventSessionViewSet)
router.register(r'ping_logs', PingLogViewSet)
router.register(r'targets', TargetViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/', include([
        path('', include(router.urls)),
        path('auth/login/', AdminLoginView.as_view(), name='admin-login'),
        path('ping_data/', PingDataView.as_view(), name='ping_data'),
        path('netops_agent_core/', NetOpsAgentCoreView.as_view(), name='netops_agent_core'),
        path('train_model/', TrainModelView.as_view(), name='train_model'),
        path('maintenance/run/', DatabaseMaintenanceView.as_view(), name='db-maintenance'),
    ])),
]
