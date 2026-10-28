from django.urls import include, path
from webapp import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/health", views.health),
    path("api/auth/login", views.login_view),
    path("api/auth/me", views.me),
    path("api/auth/logout", views.logout_view),
    path("api/summary", views.summary),
    path("api/workers", views.workers),
    path("api/workers/search", views.worker_search),
    path("api/workers/<str:worker_id>", views.worker_detail),
    path("api/workers/<str:worker_id>/status", views.worker_status),
    path("api/workers/<str:worker_id>/photo", views.worker_photo),
    path("api/workers/<str:worker_id>/id-card", views.worker_card),
    path("api/gate/scan", views.gate_scan),
    path("api/gate/transactions", views.gate_history),
    path("api/gate/report", views.gate_report),
    path("api/visitors", views.visitors),
    path("api/visitors/<str:visitor_id>", views.visitor_detail),
    path("api/visitors/<str:visitor_id>/photo", views.visitor_photo),
    path("api/visitors/<str:visitor_id>/id-card", views.visitor_card),
    path("api/canteen/scan", views.canteen_scan),
    path("api/canteen/transactions", views.canteen_history),
    path("api/canteen/report", views.canteen_report),
]
