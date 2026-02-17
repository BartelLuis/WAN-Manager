from django import forms

from .models import (
    Standort,
    Verwaltung,
    Vertrag,
    WanLeitung,
    WanBeauftragung,
    WanBeauftragungProviderKontext,
    Provider,
    ProviderZusatzoption,
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
            "arbeitsplaetze",
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
        fields = [
            "name",
            "kuerzel",
            "kundennummer",
            "kontakt_name",
            "kontakt_mail",
            "kontakt_tel",
            "anfrage_template_text",
            "bemerkung",
        ]


class ProviderZusatzoptionForm(forms.ModelForm):
    class Meta:
        model = ProviderZusatzoption
        fields = [
            "provider",
            "name",
            "beschreibung",
            "kosten_monat_netto",
            "kosten_einmalig_netto",
            "aktiv",
        ]


class TarifForm(forms.ModelForm):
    class Meta:
        model = Tarif
        fields = ["provider", "name", "beschreibung", "bandbreite_down_mbit", "bandbreite_up_mbit", "medium", "bemerkung"]


class VertragForm(forms.ModelForm):
    """
    Vertrag-Form mit:
    - Verwaltung einschränken per user.profile.verwaltung (IT-Beauftragter)
    - Kostenstelle Dropdown aus Verwaltungskürzeln
    - provider (Textfeld) automatisch aus provider_ref, falls gesetzt
    """

    class Meta:
        model = Vertrag
        fields = [
            "verwaltung",
            "provider_ref",
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
        labels = {
            "verwaltung": "Verwaltung",
            "vertragsnummer": "Vertragsnummer",
            "kosten_monat_netto": "Kosten (netto/Monat)",
            "provider_ref": "Provider",
        }

    def __init__(self, *args, **kwargs):
        # 🔥 user darf NICHT an super() weitergegeben werden
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # --- Verwaltung einschränken für IT-Beauftragte (wenn Profile gesetzt) ---
        if user and hasattr(user, "profile") and getattr(user.profile, "verwaltung_id", None):
            self.fields["verwaltung"].queryset = Verwaltung.objects.filter(id=user.profile.verwaltung_id)
            self.fields["verwaltung"].initial = user.profile.verwaltung_id

            # extrem wichtig: instance direkt setzen, damit niemand irgendwo vertrag.verwaltung liest und es knallt
            if not getattr(self.instance, "verwaltung_id", None):
                self.instance.verwaltung_id = user.profile.verwaltung_id

        # --- Kostenstelle Dropdown: Verwaltungskürzel ---
        verwaltungen = Verwaltung.objects.all().order_by("name")
        choices = [("", "---------")]
        for v in verwaltungen:
            label = f"{v.kuerzel} - {v.name}" if v.kuerzel else v.name
            choices.append((v.kuerzel or v.name, label))
        if "kostenstelle" in self.fields:
            self.fields["kostenstelle"].choices = choices

        # --- Provider queryset sortiert ---
        if "provider_ref" in self.fields:
            self.fields["provider_ref"].queryset = Provider.objects.all().order_by("name")

        # --- Wenn bestehender Vertrag: Kostenstelle initial aus Verwaltungskürzel setzen ---
        if self.instance and self.instance.pk and getattr(self.instance, "verwaltung_id", None):
            verwaltung = self.instance.verwaltung
            if getattr(verwaltung, "kuerzel", None):
                self.initial.setdefault("kostenstelle", verwaltung.kuerzel)

    def clean(self):
        cleaned = super().clean()
        provider_ref = cleaned.get("provider_ref")
        provider_text = cleaned.get("provider")

        # Wenn provider_ref gesetzt, aber provider (Textfeld) leer → automatisch füllen
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
            "medium",
            "vlan_id",
            "ip_adressbereich",
            "nat_aktiv",
            "cpe_geraet",
            "cpe_management_ip",
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        cleaned = getattr(self, "cleaned_data", {})

        provider_ref = cleaned.get("provider_ref")
        tarif_ref = cleaned.get("tarif_ref")

        if tarif_ref:
            if not provider_ref:
                provider_ref = tarif_ref.provider
                instance.provider_ref = provider_ref

            if not instance.provider:
                instance.provider = tarif_ref.provider.kuerzel or tarif_ref.provider.name

            if not instance.bezeichnung:
                instance.bezeichnung = tarif_ref.name

            if instance.bandbreite_down_mbit is None and tarif_ref.bandbreite_down_mbit is not None:
                instance.bandbreite_down_mbit = tarif_ref.bandbreite_down_mbit

            if instance.bandbreite_up_mbit is None and tarif_ref.bandbreite_up_mbit is not None:
                instance.bandbreite_up_mbit = tarif_ref.bandbreite_up_mbit

            if not instance.medium and tarif_ref.medium:
                instance.medium = tarif_ref.medium

        if not instance.provider and provider_ref:
            instance.provider = provider_ref.kuerzel or provider_ref.name

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class WanBeauftragungForm(forms.ModelForm):
    class Meta:
        model = WanBeauftragung
        fields = [
            "standort",
            "bestehende_leitung",
            "angefragte_provider",
            "titel",
            "ticket_nummer",
            "prioritaet",
            "status",
            "bedarf_down_mbit",
            "bedarf_up_mbit",
            "umsetzung_bis",
            "kostenrahmen_monat_netto",
            "kostenrahmen_einmalig_netto",
            "begruendung",
            "bemerkung",
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        standorte = Standort.objects.select_related("verwaltung").order_by("standort_code")
        leitungen = WanLeitung.objects.select_related("standort", "standort__verwaltung").order_by(
            "standort__standort_code", "bezeichnung", "provider"
        )

        if user and hasattr(user, "profile") and getattr(user.profile, "verwaltung_id", None):
            standorte = standorte.filter(verwaltung_id=user.profile.verwaltung_id)
            leitungen = leitungen.filter(standort__verwaltung_id=user.profile.verwaltung_id)

            if not getattr(self.instance, "standort_id", None):
                first_standort = standorte.first()
                if first_standort:
                    self.initial.setdefault("standort", first_standort.pk)

        self.fields["standort"].queryset = standorte
        self.fields["bestehende_leitung"].queryset = leitungen
        self.fields["angefragte_provider"].queryset = Provider.objects.order_by("name")
        self.fields["angefragte_provider"].required = False

    def clean(self):
        cleaned = super().clean()
        standort = cleaned.get("standort")
        bestehende_leitung = cleaned.get("bestehende_leitung")

        if bestehende_leitung and standort and bestehende_leitung.standort_id != standort.id:
            self.add_error(
                "bestehende_leitung",
                "Die bestehende Leitung muss zum ausgewaehlten Standort gehoeren.",
            )

        return cleaned


class WanBeauftragungProviderKontextForm(forms.ModelForm):
    class Meta:
        model = WanBeauftragungProviderKontext
        fields = [
            "tarif",
            "zusatzoptionen",
            "template_override_text",
            "anfrage_notiz",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        provider = getattr(self.instance, "provider", None)
        if provider:
            self.fields["tarif"].queryset = Tarif.objects.filter(provider=provider).order_by("name")
            self.fields["zusatzoptionen"].queryset = ProviderZusatzoption.objects.filter(
                provider=provider, aktiv=True
            ).order_by("name")
        else:
            self.fields["tarif"].queryset = Tarif.objects.none()
            self.fields["zusatzoptionen"].queryset = ProviderZusatzoption.objects.none()
        self.fields["zusatzoptionen"].required = False

    def clean(self):
        cleaned = super().clean()
        provider = getattr(self.instance, "provider", None)
        tarif = cleaned.get("tarif")
        zusatzoptionen = cleaned.get("zusatzoptionen")

        if provider and tarif and tarif.provider_id != provider.id:
            self.add_error("tarif", "Der gewaehlte Tarif gehoert nicht zum Provider.")

        if provider and zusatzoptionen:
            wrong = [z.name for z in zusatzoptionen if z.provider_id != provider.id]
            if wrong:
                self.add_error("zusatzoptionen", "Mindestens eine Zusatzoption gehoert nicht zum Provider.")

        return cleaned
