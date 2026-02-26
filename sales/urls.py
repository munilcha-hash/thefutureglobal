from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('set-region/<str:region>/', views.set_region, name='set_region'),
    path('pnl/<int:year>/<int:month>/', views.monthly_pnl, name='monthly_pnl'),
    path('brand/<str:brand_code>/<int:year>/<int:month>/', views.brand_detail, name='brand_detail'),
    path('channel/', views.channel_analysis, name='channel_analysis'),
    path('orders/shopify/', views.shopify_orders, name='shopify_orders'),
    path('orders/tiktok/', views.tiktok_orders, name='tiktok_orders'),
    path('orders/shopee/', views.shopee_orders, name='shopee_orders'),
    path('orders/qoo10/', views.qoo10_orders, name='qoo10_orders'),
    path('upload/', views.upload_excel, name='upload_excel'),
    path('upload/raw/', views.upload_raw, name='upload_raw'),
    path('api/upload-excel/', views.api_upload_excel, name='api_upload_excel'),
    path('api/upload-raw/', views.api_upload_raw, name='api_upload_raw'),
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/pnl-data/<int:year>/<int:month>/', views.api_pnl_data, name='api_pnl_data'),
]
