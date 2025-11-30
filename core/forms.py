from django import forms

from .models import Standort, Verwaltung, Vertrag, WanLeitung


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
        # Standortkürzel wird automatisch generiert -> nur anzeigen, nicht bearbeitbar
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

        # Wenn eine Verwaltung gesetzt ist, default auf deren Kürzel
        if self.instance and self.instance.verwaltung and self.instance.verwaltung.kuerzel:
            self.initial.setdefault("kostenstelle", self.instance.verwaltung.kuerzel)


class WanLeitungForm(forms.ModelForm):
    class Meta:
        model = WanLeitung
        fields = [
            "standort",
            "vertrag",
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
