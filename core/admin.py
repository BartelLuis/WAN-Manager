from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Verwaltung,
    Standort,
    Vertrag,
    WanLeitung,
    UserProfile,
    Provider,
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


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "kuerzel", "kundennummer", "kontakt_name")
    search_fields = ("name", "kuerzel", "kundennummer", "kontakt_name")


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


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
