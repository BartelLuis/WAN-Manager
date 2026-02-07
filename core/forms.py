from django import forms

from .models import (
    Standort,
    Verwaltung,
    Vertrag,
    WanLeitung,
    Provider,
    Tarif,
)


class StandortForm(forms.ModelForm):
    class Meta:
        model = Standort
        fields = [
            "verwaltung",
            "name",
            "standort_code",
            "adresse_strasse",
            "adresse_plz",
            "adresse_ort",
            "arbeitsplaetze",  # <-- NEU
            "bemerkung",
            "aktiv",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "standort_code" in self.fields:
            self.fields["standort_code"].disabled = True
            self.fields["standort_code"].required = False
            self.fields["standort_code"].label = "Standortkürzel (automatisch)"


class VerwaltungForm(forms.ModelForm):
    class Meta:
        model = Verwaltung
        fields = ["name", "kuerzel", "typ"]


class ProviderForm(forms.ModelForm):
    class Meta:
        model = Provider
        fields = ["name", "kuerzel", "kundennummer", "kontakt_name", "kontakt_mail", "kontakt_tel", "bemerkung"]


class TarifForm(forms.ModelForm):
    class Meta:
        model = Tarif
        fields = ["provider", "name", "beschreibung", "bandbreite_down_mbit", "bandbreite_up_mbit", "medium", "bemerkung"]


class VertragForm(forms.ModelForm):
    kostenstelle = forms.ChoiceField(required=False, label="Kostenstelle (Verwaltungskürzel)")

    class Meta:
        model = Vertrag
        fields = [
            "verwaltung",
            "provider_ref",
            "provider",
            "vertragsnummer",
            "rahmenvertrag",
            "bezeichnung",
            "laufzeit_von",
            "laufzeit_bis",
            "kuendigungsfrist_tage",
            "kosten_monat_netto",
            "kosten_einmalig_netto",
            "kostenstelle",
            "rechnungsempfaenger",
            "bemerkung_vertrag",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        verwaltungen = Verwaltung.objects.all().order_by("name")
        choices = [("", "---------")]
        for v in verwaltungen:
            label = f"{v.kuerzel} - {v.name}" if v.kuerzel else v.name
            choices.append((v.kuerzel or v.name, label))
        self.fields["kostenstelle"].choices = choices

        if "provider_ref" in self.fields:
            self.fields["provider_ref"].queryset = Provider.objects.all().order_by("name")

        if self.instance and self.instance.pk and getattr(self.instance, "verwaltung_id", None):
            verwaltung = self.instance.verwaltung
            if verwaltung.kuerzel:
                self.initial.setdefault("kostenstelle", verwaltung.kuerzel)

    def clean(self):
        cleaned = super().clean()
        provider_ref = cleaned.get("provider_ref")
        provider_text = cleaned.get("provider")
        if provider_ref and not provider_text:
            cleaned["provider"] = provider_ref.kuerzel or provider_ref.name
        return cleaned


class WanLeitungForm(forms.ModelForm):
    class Meta:
        model = WanLeitung
        fields = [
            "standort",
            "vertrag",
            "provider_ref",
            "tarif_ref",
            "bezeichnung",
            "provider",
            "anschlussart",
            "bandbreite_down_mbit",
            "bandbreite_up_mbit",
            "medium",
            "vlan_id",
            "ip_adressbereich",
            "nat_aktiv",
            "cpe_geraet",
            "cpe_management_ip",
            "backup_leitung",
            "status",
            "inbetriebnahme_datum",
            "ausserbetriebnahme_datum",
            "bemerkung_technik",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "provider_ref" in self.fields:
            self.fields["provider_ref"].queryset = Provider.objects.all().order_by("name")
        if "tarif_ref" in self.fields:
            self.fields["tarif_ref"].queryset = Tarif.objects.select_related("provider").order_by(
                "provider__name", "name"
            )

    def clean(self):
        cleaned = super().clean()

        provider_ref = cleaned.get("provider_ref")
        tarif_ref = cleaned.get("tarif_ref")

        provider_text = cleaned.get("provider")
        bezeichnung = cleaned.get("bezeichnung")
        down = cleaned.get("bandbreite_down_mbit")
        up = cleaned.get("bandbreite_up_mbit")
        medium = cleaned.get("medium")

        if tarif_ref:
            if not provider_ref:
                cleaned["provider_ref"] = tarif_ref.provider
                provider_ref = tarif_ref.provider

            if not provider_text:
                cleaned["provider"] = tarif_ref.provider.kuerzel or tarif_ref.provider.name

            if not bezeichnung:
                cleaned["bezeichnung"] = tarif_ref.name

            if not down and tarif_ref.bandbreite_down_mbit is not None:
                cleaned["bandbreite_down_mbit"] = tarif_ref.bandbreite_down_mbit
            if not up and tarif_ref.bandbreite_up_mbit is not None:
                cleaned["bandbreite_up_mbit"] = tarif_ref.bandbreite_up_mbit

            if not medium and tarif_ref.medium:
                cleaned["medium"] = tarif_ref.medium

        elif provider_ref and not provider_text:
            cleaned["provider"] = provider_ref.kuerzel or provider_ref.name

        return cleaned
