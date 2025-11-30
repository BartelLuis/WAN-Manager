from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Verwaltung, Standort, Vertrag, WanLeitung, UserProfile


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
    list_display = ("provider", "vertragsnummer", "verwaltung", "laufzeit_von", "laufzeit_bis", "kosten_monat_netto")
    list_filter = ("verwaltung", "provider", "rahmenvertrag")
    search_fields = ("provider", "vertragsnummer", "bezeichnung")


@admin.register(WanLeitung)
class WanLeitungAdmin(admin.ModelAdmin):
    list_display = ("__str__", "standort", "vertrag", "status")
    list_filter = ("status", "standort__verwaltung", "provider")
    search_fields = ("provider", "bezeichnung", "standort__name", "standort__standort_code")


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


# Standard-User-Admin durch unsere Variante mit Inline ersetzen
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
