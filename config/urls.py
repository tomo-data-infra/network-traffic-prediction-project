"""
URL configuration for the Network Traffic Project.
Maps public REST API routes to core viewsets, custom ML endpoints, and background agents.
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from calendar_api.views import EventSessionViewSet, PingLogViewSet, TargetViewSet, TrainModelView, PingDataView, DatabaseMaintenanceView, NetOpsAgentCoreView

# Initialize Rest Framework Router for automated CRUD endpoints
router = DefaultRouter()
router.register(r'event_sessions', EventSessionViewSet)
router.register(r'ping_logs', PingLogViewSet)
router.register(r'targets', TargetViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Unified structural API grouping
    path('api/', include([
        # Standard automated viewset routes (e.g., http://localhost:8000/api/xxxxxx/)
        path('', include(router.urls)),
        
        # Custom ML Analytics Data Feed Endpoint (http://localhost:8000/api/ping_data/)
        path('ping_data/', PingDataView.as_view(), name='ping_data'),

        # Ingestion Text-to-SQL AI Agent Interface Gateway (http://localhost:8000/api/netops_agent_core/)
        path('netops_agent_core/', NetOpsAgentCoreView.as_view(), name='netops_agent_core'),

        # Baseline Machine Learning Model Retraining Trigger (http://localhost:8000/api/train_model/)
        path('train_model/', TrainModelView.as_view(), name='train_model'),

        # Operational Database Maintenance Action Route (http://localhost:8000/api/maintenance/run/)
        path('maintenance/run/', DatabaseMaintenanceView.as_view(), name='db-maintenance'),
    ])),
]
