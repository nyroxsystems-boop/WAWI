from django.urls import path

from . import views

app_name = 'wawitest'

urlpatterns = [
    path('', views.dashboard_home, name='dashboard'),
    path('test/wawi/create/', views.create_document, name='create'),
    path('test/wawi/retry/<int:document_id>/', views.retry_document, name='retry'),
    path('test/wawi/fail/<int:document_id>/', views.force_fail, name='fail'),
    path('test/wawi/run-one/', views.run_one, name='run_one'),
    # Support both with and without trailing slash to avoid 404 on OPTIONS preflight
    path('api/bot/health', views.bot_health, name='bot-health'),
    path('api/bot/health/', views.bot_health, name='bot-health-slash'),
    path('api/dashboard/orders', views.dashboard_orders, name='dashboard-orders'),
    path('api/dashboard/orders/', views.dashboard_orders, name='dashboard-orders-slash'),
]
