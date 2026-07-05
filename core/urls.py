from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("my-tasks/", views.my_tasks, name="my_tasks"),
    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("filters/save/", views.save_filter, name="save_filter"),
    path("filters/<int:pk>/apply/", views.apply_filter, name="apply_filter"),
    path("notes/<str:model_name>/<int:object_id>/add/", views.add_object_note, name="add_object_note"),
    path("stoerungen/", views.stoerung_list, name="stoerung_list"),
    path("stoerungen/neu/", views.stoerung_create, name="stoerung_create"),
    path("stoerungen/<int:pk>/", views.stoerung_detail, name="stoerung_detail"),
    path("stoerungen/<int:pk>/bearbeiten/", views.stoerung_update, name="stoerung_update"),
    path("provider-scorecard/", views.provider_scorecard, name="provider_scorecard"),
    path("kalender/", views.ops_calendar, name="ops_calendar"),
    path("reports/interactive/", views.reports_interactive, name="reports_interactive"),
    path("standort-map/", views.standort_map, name="standort_map"),
    path("vertragswarnungen/", views.contract_warnings, name="contract_warnings"),
    path("kostenanalyse/", views.cost_analysis, name="cost_analysis"),
    path("redundanzcheck/", views.redundancy_check, name="redundancy_check"),
    path("self-service/", views.self_service, name="self_service"),
    path("datenqualitaet/", views.data_quality_center, name="data_quality_center"),
    path("dokumente/<str:model_name>/<int:object_id>/neu/", views.dokument_mappe_create, name="dokument_mappe_create"),
    path("dokumente/mappe/<int:pk>/", views.dokument_mappe_detail, name="dokument_mappe_detail"),

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
    path("beauftragungen/<int:pk>/genehmigen/", views.beauftragung_approve, name="beauftragung_approve"),
    path("beauftragungen/<int:pk>/freigabestufen/neu/", views.approval_step_create, name="approval_step_create"),
    path("beauftragungen/<int:pk>/status/<str:status>/", views.beauftragung_set_status, name="beauftragung_set_status"),

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
    path(
        "beauftragungen/<int:beauftragung_pk>/provider/<int:provider_pk>/sent/",
        views.beauftragung_provider_anfrage_sent,
        name="beauftragung_provider_anfrage_sent",
    ),
    path("erinnerungen/", views.erinnerung_list, name="erinnerung_list"),
    path("erinnerungen/<int:pk>/done/", views.erinnerung_quick_done, name="erinnerung_quick_done"),
    path("reports/vertraege.csv", views.report_vertraege_csv, name="report_vertraege_csv"),
    path("reports/beauftragungen.csv", views.report_beauftragungen_csv, name="report_beauftragungen_csv"),
    path("imports/vertraege/", views.import_vertraege_csv, name="import_vertraege_csv"),

    path("vertraege/", views.vertrag_list, name="vertrag_list"),
    path("vertraege/neu/", views.vertrag_create, name="vertrag_create"),
    path("vertraege/<int:pk>/", views.vertrag_detail, name="vertrag_detail"),
    path("vertraege/<int:pk>/bearbeiten/", views.vertrag_update, name="vertrag_update"),
]
