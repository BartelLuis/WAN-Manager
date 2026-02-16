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
    list_display = ("titel", "standort", "status", "prioritaet", "angefragt_am", "umsetzung_bis", "erstellt_von")
    list_filter = ("status", "prioritaet", "standort__verwaltung")
    search_fields = ("titel", "ticket_nummer", "standort__name", "standort__standort_code")
    filter_horizontal = ("angefragte_provider",)


@admin.register(WanBeauftragungProviderKontext)
class WanBeauftragungProviderKontextAdmin(admin.ModelAdmin):
    list_display = ("beauftragung", "provider", "tarif")
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
    list_display = ("id", "mbit_pro_arbeitsplatz")

    def has_add_permission(self, request):
        if GlobalSettings.objects.exists():
            return False
        return super().has_add_permission(request)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
