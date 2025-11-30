from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("verwaltungen/", views.verwaltung_list, name="verwaltung_list"),
    path("verwaltungen/neu/", views.verwaltung_create, name="verwaltung_create"),
    path("verwaltungen/<int:pk>/", views.verwaltung_detail, name="verwaltung_detail"),
    path("verwaltungen/<int:pk>/bearbeiten/", views.verwaltung_update, name="verwaltung_update"),

    path("standorte/", views.standort_list, name="standort_list"),
    path("standorte/neu/", views.standort_create, name="standort_create"),
    path("standorte/<int:pk>/", views.standort_detail, name="standort_detail"),
    path("standorte/<int:pk>/bearbeiten/", views.standort_update, name="standort_update"),

    path("leitungen/", views.wanleitung_list, name="wanleitung_list"),
    path("leitungen/neu/", views.wanleitung_create, name="wanleitung_create"),
    path("leitungen/<int:pk>/", views.wanleitung_detail, name="wanleitung_detail"),
    path("leitungen/<int:pk>/bearbeiten/", views.wanleitung_update, name="wanleitung_update"),

    path("vertraege/", views.vertrag_list, name="vertrag_list"),
    path("vertraege/neu/", views.vertrag_create, name="vertrag_create"),
    path("vertraege/<int:pk>/", views.vertrag_detail, name="vertrag_detail"),
    path("vertraege/<int:pk>/bearbeiten/", views.vertrag_update, name="vertrag_update"),
]
