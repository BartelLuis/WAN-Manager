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

    path("beauftragungen/", views.beauftragung_list, name="beauftragung_list"),
    path("beauftragungen/neu/", views.beauftragung_create, name="beauftragung_create"),
    path("beauftragungen/<int:pk>/", views.beauftragung_detail, name="beauftragung_detail"),
    path("beauftragungen/<int:pk>/bearbeiten/", views.beauftragung_update, name="beauftragung_update"),

    path("provider/", views.provider_list, name="provider_list"),
    path("provider/neu/", views.provider_create, name="provider_create"),
    path("provider/<int:pk>/", views.provider_detail, name="provider_detail"),
    path("provider/<int:pk>/bearbeiten/", views.provider_update, name="provider_update"),
    path("provider-optionen/", views.provider_option_list, name="provider_option_list"),
    path("provider-optionen/neu/", views.provider_option_create, name="provider_option_create"),
    path("provider-optionen/<int:pk>/bearbeiten/", views.provider_option_update, name="provider_option_update"),

    path("tarife/", views.tarif_list, name="tarif_list"),
    path("tarife/neu/", views.tarif_create, name="tarif_create"),
    path("tarife/<int:pk>/", views.tarif_detail, name="tarif_detail"),
    path("tarife/<int:pk>/bearbeiten/", views.tarif_update, name="tarif_update"),

    path(
        "beauftragungen/<int:beauftragung_pk>/provider/<int:provider_pk>/",
        views.beauftragung_provider_kontext_update,
        name="beauftragung_provider_kontext_update",
    ),

    path("vertraege/", views.vertrag_list, name="vertrag_list"),
    path("vertraege/neu/", views.vertrag_create, name="vertrag_create"),
    path("vertraege/<int:pk>/", views.vertrag_detail, name="vertrag_detail"),
    path("vertraege/<int:pk>/bearbeiten/", views.vertrag_update, name="vertrag_update"),
]
