from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Verwaltung,
    Standort,
    Vertrag,
    WanLeitung,
    WanBeauftragung,
    WanBeauftragungProviderKontext,
    UserProfile,
    Provider,
    ProviderZusatzoption,
    Tarif,
    GlobalSettings,
    AuditLog,
    Erinnerung,
    DokumentAnhang,
    DokumentMappe,
    DokumentVersion,
    ObjektNotiz,
    UserNotification,
    SavedFilter,
    LeitungsStoerung,
    ProviderBewertung,
    ObjektBerechtigung,
)


@admin.register(Verwaltung)
class VerwaltungAdmin(admin.ModelAdmin):
    list_display = ("name", "kuerzel", "typ")
    list_filter = ("typ",)
    search_fields = ("name", "kuerzel")


@admin.register(Standort)
class StandortAdmin(admin.ModelAdmin):
    list_display = ("name", "standort_code", "verwaltung", "adresse_ort", "aktiv")
    list_filter = ("verwaltung", "aktiv")
    search_fields = ("name", "standort_code", "adresse_ort", "adresse_strasse")


@admin.register(Vertrag)
class VertragAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "vertragsnummer",
        "verwaltung",
        "provider_ref",
        "laufzeit_von",
        "laufzeit_bis",
        "kosten_monat_netto",
    )
    list_filter = ("verwaltung", "provider_ref", "provider", "rahmenvertrag")
    search_fields = ("provider", "vertragsnummer", "bezeichnung")


@admin.register(WanLeitung)
class WanLeitungAdmin(admin.ModelAdmin):
    list_display = ("__str__", "standort", "provider_ref", "tarif_ref", "vertrag","status")
    list_filter = ("status", "standort__verwaltung", "provider_ref")
    search_fields = (
        "provider",
        "bezeichnung",
        "standort__name",
        "standort__standort_code",
    )


@admin.register(WanBeauftragung)
class WanBeauftragungAdmin(admin.ModelAdmin):
    list_display = ("titel", "standort", "status", "genehmigt", "prioritaet", "angefragt_am", "umsetzung_bis", "erstellt_von")
    list_filter = ("status", "prioritaet", "standort__verwaltung")
    search_fields = ("titel", "ticket_nummer", "standort__name", "standort__standort_code")
    filter_horizontal = ("angefragte_provider",)


@admin.register(WanBeauftragungProviderKontext)
class WanBeauftragungProviderKontextAdmin(admin.ModelAdmin):
    list_display = ("beauftragung", "provider", "tarif", "angebot_kosten_monat_netto", "angebot_umsetzungstage", "empfohlen")
    list_filter = ("provider", "beauftragung__standort__verwaltung")
    search_fields = ("beauftragung__titel", "provider__name", "provider__kuerzel")
    filter_horizontal = ("zusatzoptionen",)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "kuerzel", "kundennummer", "kontakt_name")
    search_fields = ("name", "kuerzel", "kundennummer", "kontakt_name")


@admin.register(ProviderZusatzoption)
class ProviderZusatzoptionAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "kosten_monat_netto", "kosten_einmalig_netto", "aktiv")
    list_filter = ("provider", "aktiv")
    search_fields = ("name", "beschreibung", "provider__name", "provider__kuerzel")


@admin.register(Tarif)
class TarifAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "bandbreite_down_mbit", "bandbreite_up_mbit", "medium")
    list_filter = ("provider", "medium")
    search_fields = ("name", "beschreibung", "provider__name", "provider__kuerzel")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "verwaltung")
    list_filter = ("verwaltung",)
    search_fields = ("user__username", "user__first_name", "user__last_name")


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "mbit_pro_arbeitsplatz", "ticket_system_email", "ticket_header_name")

    def has_add_permission(self, request):
        if GlobalSettings.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(Erinnerung)
class ErinnerungAdmin(admin.ModelAdmin):
    list_display = ("titel", "typ", "status", "faellig_am", "zugewiesen_an", "vertrag", "beauftragung")
    list_filter = ("typ", "status", "faellig_am")
    search_fields = ("titel", "notiz", "vertrag__vertragsnummer", "beauftragung__titel")


@admin.register(DokumentAnhang)
class DokumentAnhangAdmin(admin.ModelAdmin):
    list_display = ("bezeichnung", "content_type", "object_id", "hochgeladen_am", "hochgeladen_von")
    list_filter = ("content_type", "hochgeladen_am")
    search_fields = ("bezeichnung", "bemerkung")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "model_label", "object_id", "action", "actor")
    list_filter = ("action", "model_label", "created_at")
    search_fields = ("model_label", "object_repr")
    readonly_fields = ("created_at", "model_label", "object_id", "action", "object_repr", "changed_fields", "snapshot", "actor", "content_type")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ObjektNotiz)
class ObjektNotizAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "erstellt_von", "erstellt_am")
    list_filter = ("content_type", "erstellt_am")
    search_fields = ("text",)


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "titel", "gelesen", "erstellt_am")
    list_filter = ("gelesen", "erstellt_am")
    search_fields = ("titel", "nachricht", "user__username")


@admin.register(SavedFilter)
class SavedFilterAdmin(admin.ModelAdmin):
    list_display = ("user", "target", "name", "created_at")
    list_filter = ("target",)
    search_fields = ("name", "querystring", "user__username")


@admin.register(LeitungsStoerung)
class LeitungsStoerungAdmin(admin.ModelAdmin):
    list_display = ("titel", "wanleitung", "provider", "status", "impact", "geoeffnet_am", "behoben_am")
    list_filter = ("status", "impact", "wanleitung__standort__verwaltung", "provider")
    search_fields = ("titel", "ticket_nummer", "wanleitung__standort__name", "wanleitung__standort__standort_code")


@admin.register(ProviderBewertung)
class ProviderBewertungAdmin(admin.ModelAdmin):
    list_display = ("provider", "beauftragung", "gesamt_score", "erstellt_von", "erstellt_am")
    list_filter = ("provider", "erstellt_am")
    search_fields = ("provider__name", "beauftragung__titel", "kommentar")


@admin.register(DokumentMappe)
class DokumentMappeAdmin(admin.ModelAdmin):
    list_display = ("titel", "status", "content_type", "object_id", "erstellt_am", "erstellt_von")
    list_filter = ("status", "content_type")
    search_fields = ("titel", "bemerkung")


@admin.register(DokumentVersion)
class DokumentVersionAdmin(admin.ModelAdmin):
    list_display = ("mappe", "version", "freigegeben", "hochgeladen_am", "hochgeladen_von")
    list_filter = ("freigegeben", "hochgeladen_am")
    search_fields = ("mappe__titel", "changelog")


@admin.register(ObjektBerechtigung)
class ObjektBerechtigungAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "erlaubt", "content_type", "object_id", "erstellt_am")
    list_filter = ("action", "erlaubt", "content_type")
    search_fields = ("user__username",)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
