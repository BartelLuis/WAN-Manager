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
        fields = [
            "name",
            "kuerzel",
            "typ",
        ]


class VertragForm(forms.ModelForm):
    # Kostenstelle als Dropdown über Verwaltungskürzel
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
            label = v.name
            if v.kuerzel:
                label = f"{v.kuerzel} - {v.name}"
            choices.append((v.kuerzel or v.name, label))

        self.fields["kostenstelle"].choices = choices

        if self.instance and self.instance.verwaltung and self.instance.verwaltung.kuerzel:
            self.initial.setdefault("kostenstelle", self.instance.verwaltung.kuerzel)

        # Provider-Auswahl sortiert
        if "provider_ref" in self.fields:
            self.fields["provider_ref"].queryset = Provider.objects.all().order_by("name")

    def clean(self):
        cleaned = super().clean()

        provider_ref = cleaned.get("provider_ref")
        provider_text = cleaned.get("provider")

        # Wenn ein Provider-Stammdatensatz gewählt ist, aber kein Freitext-Provider gesetzt ist:
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

        # Wenn ein Tarif gewählt wurde, können wir Felder vorbelegen,
        # aber nur dort, wo noch nichts eingetragen ist:
        if tarif_ref:
            # Provider aus Tarif übernehmen, falls noch nicht gewählt
            if not provider_ref:
                cleaned["provider_ref"] = tarif_ref.provider
                provider_ref = tarif_ref.provider

            # Freitext-Provider füllen, falls leer
            if not provider_text:
                cleaned["provider"] = tarif_ref.provider.kuerzel or tarif_ref.provider.name

            # Bezeichnung / Tarifname
            if not bezeichnung:
                cleaned["bezeichnung"] = tarif_ref.name

            # Bandbreiten
            if not down and tarif_ref.bandbreite_down_mbit is not None:
                cleaned["bandbreite_down_mbit"] = tarif_ref.bandbreite_down_mbit
            if not up and tarif_ref.bandbreite_up_mbit is not None:
                cleaned["bandbreite_up_mbit"] = tarif_ref.bandbreite_up_mbit

            # Medium
            if not medium and tarif_ref.medium:
                cleaned["medium"] = tarif_ref.medium

        # Falls nur Provider gewählt und kein Freitext-Provider eingetragen:
        elif provider_ref and not provider_text:
            cleaned["provider"] = provider_ref.kuerzel or provider_ref.name

        return cleaned
