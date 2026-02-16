import re
from collections import defaultdict

from django.db import models
from django.contrib.auth.models import User


class Verwaltung(models.Model):
    TYP_KREIS = "kreisverwaltung"
    TYP_AMT = "amtsverwaltung"
    TYP_STADT = "stadtverwaltung"
    TYP_GEMEINDE = "gemeindeverwaltung"

    TYP_CHOICES = [
        (TYP_KREIS, "Kreisverwaltung"),
        (TYP_AMT, "Amtsverwaltung"),
        (TYP_STADT, "Stadtverwaltung"),
        (TYP_GEMEINDE, "Gemeindeverwaltung"),
    ]

    name = models.CharField(max_length=255)
    kuerzel = models.CharField("VKZ", max_length=50, blank=True, null=True, unique=True)
    typ = models.CharField(max_length=50, choices=TYP_CHOICES, blank=True, null=True)

    class Meta:
        ordering = ["kuerzel"]

    def __str__(self):
        return self.name


class Provider(models.Model):
    name = models.CharField(max_length=255)
    kuerzel = models.CharField("Kürzel", max_length=50, blank=True, null=True)
    kundennummer = models.CharField(max_length=100, blank=True, null=True)
    kontakt_name = models.CharField("Kontakt Name", max_length=255, blank=True, null=True)
    kontakt_mail = models.EmailField("Kontakt E-Mail", blank=True, null=True)
    kontakt_tel = models.CharField("Kontakt Telefon", max_length=50, blank=True, null=True)
    anfrage_template_text = models.TextField(
        blank=True,
        null=True,
        verbose_name="Anfrage-Template (Text)",
        help_text=(
            "Platzhalter: {anbieter_name}, {anbieter_kuerzel}, {standort_name}, {standort_code}, "
            "{standort_adresse_komplett}, {verwaltung_name}, {bedarf_down_mbit}, {bedarf_up_mbit}, "
            "{umsetzung_bis}, {titel}, {ticket_nummer}, {tarif_name}, {zusatzoptionen}"
        ),
    )
    bemerkung = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        if self.kuerzel:
            return f"{self.kuerzel} - {self.name}"
        return self.name


class ProviderZusatzoption(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="zusatzoptionen")
    name = models.CharField(max_length=255)
    beschreibung = models.TextField(blank=True, null=True)
    kosten_monat_netto = models.DecimalField("Kosten p. Monat (Netto)", max_digits=10, decimal_places=2, blank=True, null=True)
    kosten_einmalig_netto = models.DecimalField("Kosten einmalig (Netto)", max_digits=10, decimal_places=2, blank=True, null=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider__name", "name"]

    def __str__(self):
        return f"{self.provider} - {self.name}"


class Tarif(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="tarife")
    name = models.CharField(max_length=255)
    beschreibung = models.TextField(blank=True, null=True)
    bandbreite_down_mbit = models.IntegerField(blank=True, null=True)
    bandbreite_up_mbit = models.IntegerField(blank=True, null=True)
    medium = models.CharField(max_length=50, blank=True, null=True)
    bemerkung = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["provider__name", "name"]

    def __str__(self):
        return f"{self.provider} - {self.name}"


class Standort(models.Model):
    verwaltung = models.ForeignKey(Verwaltung, on_delete=models.CASCADE, related_name="standorte")
    name = models.CharField(max_length=255)
    standort_code = models.CharField(max_length=50, blank=True, null=True)
    adresse_strasse = models.CharField("Straße", max_length=255, blank=True, null=True)
    adresse_plz = models.CharField("Postleitzahl", max_length=10, blank=True, null=True)
    adresse_ort = models.CharField("Ort", max_length=100, blank=True, null=True)
    gebaeude_typ = models.CharField(max_length=50, blank=True, null=True)  # wird im Frontend nicht genutzt
    arbeitsplaetze = models.PositiveIntegerField("Arbeitsplätze", default=0)  # <-- NEU
    bemerkung = models.TextField(blank=True, null=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["standort_code"]

    def __str__(self):
        if self.standort_code:
            return self.standort_code
        return self.name


    def generate_standort_code(self):
        """
        Kürzel-Verwaltung + erste 3 Buchstaben Ort + erste 3 Buchstaben Straße + Hausnummer:
        - 1     -> 001
        - 1b    -> 01b
        Beispiel: 500HUSNEU042
        """
        if not self.verwaltung or not self.verwaltung.kuerzel:
            return self.standort_code

        if not self.adresse_ort or not self.adresse_strasse:
            return self.standort_code

        verw_kz = (self.verwaltung.kuerzel or "").upper()

        def _normalize_code_text(value: str) -> str:
            if not value:
                return ""
            replacements = {
                "ä": "ae",
                "ö": "oe",
                "ü": "ue",
                "ß": "ss",
                "Ä": "Ae",
                "Ö": "Oe",
                "Ü": "Ue",
            }
            for src, dst in replacements.items():
                value = value.replace(src, dst)
            return value

        ort_clean = "".join(_normalize_code_text(self.adresse_ort).split())
        ort_part = ort_clean[:3].upper()

        street_full = (self.adresse_strasse or "").strip()
        if not street_full:
            return self.standort_code

        parts = street_full.split()
        if len(parts) == 1:
            street_name = parts[0]
            number_raw = ""
        else:
            street_name = " ".join(parts[:-1])
            number_raw = parts[-1]

        street_clean = "".join(_normalize_code_text(street_name).split())
        street_part = street_clean[:3].upper()

        hausnummer_part = ""
        if number_raw:
            m = re.match(r"(\d+)([A-Za-z]*)", number_raw)
            if m:
                digits, letters = m.groups()
                digits_fmt = digits.zfill(2) if letters else digits.zfill(3)
                hausnummer_part = f"{digits_fmt}{letters.lower()}"

        return f"{verw_kz}{ort_part}{street_part}{hausnummer_part}"

    def save(self, *args, **kwargs):
        new_code = self.generate_standort_code()
        if new_code:
            self.standort_code = new_code
        super().save(*args, **kwargs)


class Vertrag(models.Model):
    verwaltung = models.ForeignKey(Verwaltung, on_delete=models.CASCADE, related_name="vertraege")

    provider_ref = models.ForeignKey(
        Provider, on_delete=models.SET_NULL, blank=True, null=True, related_name="vertraege"
    )
    provider = models.CharField(max_length=255)

    vertragsnummer = models.CharField(max_length=100)
    rahmenvertrag = models.BooleanField(default=False)
    bezeichnung = models.CharField(max_length=255, blank=True, null=True)
    laufzeit_von = models.DateField(blank=True, null=True)
    laufzeit_bis = models.DateField(blank=True, null=True)
    kuendigungsfrist_tage = models.IntegerField(blank=True, null=True)
    kosten_monat_netto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    kosten_einmalig_netto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    kostenstelle = models.CharField(max_length=100, blank=True, null=True)
    rechnungsempfaenger = models.CharField("Rechnungsempfänger", max_length=255, blank=True, null=True)
    bemerkung_vertrag = models.TextField("Bemerkung Vertrag", blank=True, null=True)

    class Meta:
        ordering = ["provider", "vertragsnummer"]

    def __str__(self):
        return f"{self.provider} - {self.vertragsnummer}"


class WanLeitung(models.Model):
    STATUS_CHOICES = [
        ("aktiv", "Aktiv"),
        ("in_kuendigung", "In Kündigung"),
        ("geplant", "Geplant"),
        ("ausser_betrieb", "Außer Betrieb"),
    ]

    MEDIUM_CHOICES = [
        ("dsl", "DSL"),
        ("fibre", "Glasfaser"),
        ("mobile", "Mobilfunk"),
        ("cable", "Kabel"),
    ]

    standort = models.ForeignKey(Standort, on_delete=models.CASCADE, related_name="leitungen")
    vertrag = models.ForeignKey(Vertrag, on_delete=models.SET_NULL, related_name="leitungen", blank=True, null=True)


    provider_ref = models.ForeignKey(Provider, on_delete=models.SET_NULL, blank=True, null=True, related_name="leitungen")
    tarif_ref = models.ForeignKey(Tarif, on_delete=models.SET_NULL, blank=True, null=True, related_name="leitungen")

    bezeichnung = models.CharField(max_length=255, blank=True, null=True)
    provider = models.CharField(max_length=255)

    anschlussart = models.CharField(max_length=100, blank=True, null=True)
    bandbreite_down_mbit = models.IntegerField(blank=True, null=True)
    bandbreite_up_mbit = models.IntegerField(blank=True, null=True)
    medium = models.CharField(max_length=50, choices=MEDIUM_CHOICES)
    vlan_id = models.IntegerField("VLAN-ID", blank=True, null=True)
    ip_adressbereich = models.CharField("IP-Adresse(n)", max_length=50, blank=True, null=True)
    nat_aktiv = models.BooleanField("NAT Aktiv?", default=False)
    cpe_geraet = models.CharField("CPE Gerät", max_length=255, blank=True, null=True)
    cpe_management_ip = models.CharField("CPE Management IP", max_length=50, blank=True, null=True)
    backup_leitung = models.ForeignKey("self", on_delete=models.SET_NULL, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="aktiv")
    inbetriebnahme_datum = models.DateField("Inbetriebnahme-Datum", blank=True, null=True)
    ausserbetriebnahme_datum = models.DateField("Außerbetriebnahme-Datum", blank=True, null=True)
    bemerkung_technik = models.TextField("Bemerkung Technik", blank=True, null=True)

    class Meta:
        ordering = ["standort__verwaltung__name", "standort__name", "provider"]

    def __str__(self):
        label = self.bezeichnung or self.provider
        return f"{self.standort} - {label} ({self.bandbreite_down_mbit or '?'} Mbit)"


class WanBeauftragung(models.Model):
    STATUS_OFFEN = "offen"
    STATUS_IN_PRUEFUNG = "in_pruefung"
    STATUS_BEAUFTRAGT = "beauftragt"
    STATUS_UMGESETZT = "umgesetzt"
    STATUS_ABGELEHNT = "abgelehnt"
    STATUS_STORNIERT = "storniert"

    STATUS_CHOICES = [
        (STATUS_OFFEN, "Offen"),
        (STATUS_IN_PRUEFUNG, "In Pruefung"),
        (STATUS_BEAUFTRAGT, "Beauftragt"),
        (STATUS_UMGESETZT, "Umgesetzt"),
        (STATUS_ABGELEHNT, "Abgelehnt"),
        (STATUS_STORNIERT, "Storniert"),
    ]

    PRIO_NIEDRIG = "niedrig"
    PRIO_NORMAL = "normal"
    PRIO_HOCH = "hoch"
    PRIO_KRITISCH = "kritisch"

    PRIORITAET_CHOICES = [
        (PRIO_NIEDRIG, "Niedrig"),
        (PRIO_NORMAL, "Normal"),
        (PRIO_HOCH, "Hoch"),
        (PRIO_KRITISCH, "Kritisch"),
    ]

    standort = models.ForeignKey(Standort, on_delete=models.CASCADE, related_name="beauftragungen")
    bestehende_leitung = models.ForeignKey(
        WanLeitung,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="beauftragungen",
    )
    angefragte_provider = models.ManyToManyField(
        Provider,
        blank=True,
        related_name="beauftragungen",
    )
    erstellt_von = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)

    titel = models.CharField(max_length=255)
    ticket_nummer = models.CharField(max_length=100, blank=True, null=True)
    prioritaet = models.CharField(max_length=20, choices=PRIORITAET_CHOICES, default=PRIO_NORMAL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OFFEN)

    bedarf_down_mbit = models.PositiveIntegerField("Bedarf Downlink (Mbit/s)", blank=True, null=True)
    bedarf_up_mbit = models.PositiveIntegerField("Bedarf Uplink (Mbit/s)", blank=True, null=True)
    umsetzung_bis = models.DateField(blank=True, null=True)
    angefragt_am = models.DateField(auto_now_add=True)

    kostenrahmen_monat_netto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    kostenrahmen_einmalig_netto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    begruendung = models.TextField(blank=True, null=True)
    bemerkung = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-angefragt_am", "-id"]

    def __str__(self):
        return f"{self.standort} - {self.titel}"

    def _template_context(self, provider=None):
        adresse_komplett = ""
        if self.standort_id:
            teile = [
                (self.standort.adresse_strasse or "").strip(),
                " ".join([p for p in [(self.standort.adresse_plz or "").strip(), (self.standort.adresse_ort or "").strip()] if p]).strip(),
            ]
            adresse_komplett = ", ".join([t for t in teile if t])

        return {
            "anbieter_name": provider.name if provider else "",
            "anbieter_kuerzel": (provider.kuerzel or "") if provider else "",
            "standort_name": self.standort.name if self.standort_id else "",
            "standort_code": (self.standort.standort_code or "") if self.standort_id else "",
            "standort_adresse_komplett": adresse_komplett,
            "verwaltung_name": self.standort.verwaltung.name if self.standort_id else "",
            "titel": self.titel or "",
            "ticket_nummer": self.ticket_nummer or "",
            "bedarf_down_mbit": str(self.bedarf_down_mbit or ""),
            "bedarf_up_mbit": str(self.bedarf_up_mbit or ""),
            "umsetzung_bis": self.umsetzung_bis.strftime("%d.%m.%Y") if self.umsetzung_bis else "",
        }

    def render_anfrage_betreff(self, provider=None):
        standort_code = (self.standort.standort_code or "").strip() if self.standort_id else ""
        return f"WAN-Anbindung {standort_code or '-'}"

    def get_anfrage_template_text(self, provider=None):
        template = ""
        if provider and provider.anfrage_template_text:
            template = (provider.anfrage_template_text or "").strip()

        if not template:
            settings_obj = GlobalSettings.objects.filter(pk=1).first()
            template = (settings_obj.anfrage_template_text or "").strip() if settings_obj else ""

        if not template:
            template = (
                "Guten Tag,\n\n"
                "wir bitten um ein Angebot fuer folgenden WAN-Bedarf:\n"
                "- Standort: {standort_name} ({standort_code})\n"
                "- Verwaltung: {verwaltung_name}\n"
                "- Bedarf: {bedarf_down_mbit}/{bedarf_up_mbit} Mbit/s\n"
                "- Umsetzung bis: {umsetzung_bis}\n"
                "- Referenz: {titel} {ticket_nummer}\n\n"
                "Vielen Dank."
            )
        return template

    def render_anfrage_text(self, provider=None):
        template = self.get_anfrage_template_text(provider)
        try:
            return template.format_map(defaultdict(str, self._template_context(provider)))
        except (KeyError, ValueError):
            return template


class WanBeauftragungProviderKontext(models.Model):
    beauftragung = models.ForeignKey(WanBeauftragung, on_delete=models.CASCADE, related_name="provider_kontexte")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="beauftragungs_kontexte")
    tarif = models.ForeignKey(Tarif, on_delete=models.SET_NULL, blank=True, null=True, related_name="beauftragungs_kontexte")
    zusatzoptionen = models.ManyToManyField(ProviderZusatzoption, blank=True, related_name="beauftragungs_kontexte")
    template_override_text = models.TextField(blank=True, null=True)
    anfrage_notiz = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("beauftragung", "provider")
        ordering = ["provider__name"]

    def __str__(self):
        return f"{self.beauftragung} - {self.provider}"

    def render_anfrage_text(self):
        template = (self.template_override_text or "").strip()
        if not template:
            template = self.beauftragung.get_anfrage_template_text(self.provider)
        context = defaultdict(str, self.beauftragung._template_context(self.provider))
        context["tarif_name"] = self.tarif.name if self.tarif_id else ""
        context["zusatzoptionen"] = ", ".join(self.zusatzoptionen.values_list("name", flat=True))
        try:
            return template.format_map(context)
        except (KeyError, ValueError):
            return template


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    verwaltung = models.ForeignKey(Verwaltung, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return self.user.username

class GlobalSettings(models.Model):
    """
    Singleton für globale WAN-Parameter.
    """

    mbit_pro_arbeitsplatz = models.PositiveIntegerField(
        default=10,
        verbose_name="Mbit/s pro Arbeitsplatz"
    )
    anfrage_template_text = models.TextField(
        blank=True,
        null=True,
        verbose_name="WAN-Anfrage Template (Text)",
        help_text=(
            "Platzhalter: {anbieter_name}, {anbieter_kuerzel}, {standort_name}, {standort_code}, "
            "{standort_adresse_komplett}, {verwaltung_name}, {bedarf_down_mbit}, {bedarf_up_mbit}, "
            "{umsetzung_bis}, {titel}, {ticket_nummer}, {tarif_name}, {zusatzoptionen}"
        ),
    )

    def save(self, *args, **kwargs):
        self.pk = 1  # erzwingt genau einen Datensatz
        super().save(*args, **kwargs)

    def __str__(self):
        return "Globale Einstellungen"

