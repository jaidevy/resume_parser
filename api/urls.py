"""
URL configuration for the Resume Parser API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"resumes", views.ResumeViewSet, basename="resume")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", views.health_check, name="health-check"),
    path("schema/", views.data_dictionary, name="data-dictionary"),
    path("webhook/power-automate/", views.power_automate_webhook, name="power-automate-webhook"),
    path("webhook/n8n/", views.n8n_webhook, name="n8n-webhook"),
]
