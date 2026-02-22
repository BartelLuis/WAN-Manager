import re
from collections import defaultdict

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver


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
        constraints = [
            models.UniqueConstraint(fields=["provider", "name"], name="uniq_option_name_per_provider"),
        ]

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
        constraints = [
            models.UniqueConstraint(fields=["provider", "name"], name="uniq_tarif_name_per_provider"),
        ]

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
        constraints = [
            models.UniqueConstraint(
                fields=["standort_code"],
                name="uniq_standort_code_not_blank",
                condition=Q(standort_code__isnull=False) & ~Q(standort_code=""),
            ),
        ]

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
        constraints = [
            models.CheckConstraint(
                check=Q(laufzeit_von__isnull=True) | Q(laufzeit_bis__isnull=True) | Q(laufzeit_bis__gte=models.F("laufzeit_von")),
                name="vertrag_laufzeit_von_bis_valid",
            ),
            models.CheckConstraint(
                check=Q(kuendigungsfrist_tage__isnull=True) | Q(kuendigungsfrist_tage__gte=0),
                name="vertrag_kuendigungsfrist_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.provider} - {self.vertragsnummer}"

    def clean(self):
        errors = {}
        if self.laufzeit_von and self.laufzeit_bis and self.laufzeit_bis < self.laufzeit_von:
            errors["laufzeit_bis"] = "Laufzeit bis muss nach Laufzeit von liegen."
        if self.kuendigungsfrist_tage is not None and self.kuendigungsfrist_tage < 0:
            errors["kuendigungsfrist_tage"] = "Kündigungsfrist darf nicht negativ sein."
        if errors:
            raise ValidationError(errors)


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
        constraints = [
            models.CheckConstraint(
                check=Q(vlan_id__isnull=True) | (Q(vlan_id__gte=1) & Q(vlan_id__lte=4094)),
                name="wanleitung_vlan_in_valid_range",
            ),
            models.CheckConstraint(
                check=Q(inbetriebnahme_datum__isnull=True) | Q(ausserbetriebnahme_datum__isnull=True) | Q(ausserbetriebnahme_datum__gte=models.F("inbetriebnahme_datum")),
                name="wanleitung_ausserbetriebnahme_after_inbetriebnahme",
            ),
        ]

    def __str__(self):
        label = self.bezeichnung or self.provider
        return f"{self.standort} - {label} ({self.bandbreite_down_mbit or '?'} Mbit)"

    def clean(self):
        errors = {}
        if self.vlan_id is not None and not (1 <= self.vlan_id <= 4094):
            errors["vlan_id"] = "VLAN-ID muss zwischen 1 und 4094 liegen."
        if (
            self.inbetriebnahme_datum
            and self.ausserbetriebnahme_datum
            and self.ausserbetriebnahme_datum < self.inbetriebnahme_datum
        ):
            errors["ausserbetriebnahme_datum"] = "Außerbetriebnahme darf nicht vor Inbetriebnahme liegen."
        if self.tarif_ref_id and self.provider_ref_id and self.tarif_ref.provider_id != self.provider_ref_id:
            errors["tarif_ref"] = "Tarif und Provider passen nicht zusammen."
        if errors:
            raise ValidationError(errors)


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
    genehmigt = models.BooleanField(default=False)
    genehmigt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="genehmigte_beauftragungen",
    )
    genehmigt_am = models.DateTimeField(blank=True, null=True)
    genehmigungs_notiz = models.TextField(blank=True, null=True)
    ticket_gesendet_am = models.DateTimeField(blank=True, null=True)

    begruendung = models.TextField(blank=True, null=True)
    bemerkung = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-angefragt_am", "-id"]
        constraints = [
            models.CheckConstraint(
                check=Q(umsetzung_bis__isnull=True) | Q(angefragt_am__isnull=True) | Q(umsetzung_bis__gte=models.F("angefragt_am")),
                name="beauftragung_umsetzung_after_anfrage",
            ),
        ]

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
    angebot_kosten_monat_netto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    angebot_kosten_einmalig_netto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    angebot_umsetzungstage = models.PositiveIntegerField(blank=True, null=True)
    angebot_score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Subjektive Bewertung 0.0 bis 10.0",
    )
    empfohlen = models.BooleanField(default=False)
    anfrage_gesendet_am = models.DateTimeField(blank=True, null=True)
    anfrage_gesendet_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="provider_anfragen_gesendet",
    )

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


class DokumentAnhang(models.Model):
    bezeichnung = models.CharField(max_length=255)
    datei = models.FileField(upload_to="anhaenge/%Y/%m/")
    hochgeladen_am = models.DateTimeField(auto_now_add=True)
    hochgeladen_von = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    bemerkung = models.TextField(blank=True, null=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        return self.bezeichnung


class ObjektNotiz(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    text = models.TextField()
    erstellt_von = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-erstellt_am", "-id"]

    def __str__(self):
        return f"Notiz {self.content_type}#{self.object_id}"


class UserNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    titel = models.CharField(max_length=255)
    nachricht = models.TextField(blank=True, null=True)
    link = models.CharField(max_length=255, blank=True, null=True)
    gelesen = models.BooleanField(default=False)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["gelesen", "-erstellt_am", "-id"]

    def __str__(self):
        return f"{self.user} - {self.titel}"


class SavedFilter(models.Model):
    TARGET_ERINNERUNG = "erinnerung"
    TARGET_BEAUFTRAGUNG = "beauftragung"
    TARGET_STANDORT = "standort"
    TARGET_CHOICES = [
        (TARGET_ERINNERUNG, "Erinnerungen"),
        (TARGET_BEAUFTRAGUNG, "Beauftragungen"),
        (TARGET_STANDORT, "Standorte"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_filters")
    target = models.CharField(max_length=40, choices=TARGET_CHOICES)
    name = models.CharField(max_length=80)
    querystring = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target", "name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "target", "name"], name="uniq_filter_name_per_target"),
        ]

    def __str__(self):
        return f"{self.user} - {self.target} - {self.name}"


class Erinnerung(models.Model):
    STATUS_OFFEN = "offen"
    STATUS_ERLEDIGT = "erledigt"
    STATUS_UEBERFAELLIG = "ueberfaellig"
    STATUS_CHOICES = [
        (STATUS_OFFEN, "Offen"),
        (STATUS_ERLEDIGT, "Erledigt"),
        (STATUS_UEBERFAELLIG, "Überfällig"),
    ]

    TYP_VERTRAG = "vertrag"
    TYP_BEAUFTRAGUNG = "beauftragung"
    TYP_CHOICES = [
        (TYP_VERTRAG, "Vertrag"),
        (TYP_BEAUFTRAGUNG, "Beauftragung"),
    ]

    titel = models.CharField(max_length=255)
    typ = models.CharField(max_length=20, choices=TYP_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OFFEN)
    faellig_am = models.DateField()
    zugewiesen_an = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    notiz = models.TextField(blank=True, null=True)

    vertrag = models.ForeignKey(Vertrag, on_delete=models.CASCADE, blank=True, null=True, related_name="erinnerungen")
    beauftragung = models.ForeignKey(WanBeauftragung, on_delete=models.CASCADE, blank=True, null=True, related_name="erinnerungen")

    class Meta:
        ordering = ["status", "faellig_am", "id"]
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(vertrag__isnull=False) & Q(beauftragung__isnull=True) & Q(typ="vertrag"))
                    | (Q(vertrag__isnull=True) & Q(beauftragung__isnull=False) & Q(typ="beauftragung"))
                ),
                name="erinnerung_exactly_one_target",
            ),
        ]

    def __str__(self):
        return f"{self.titel} ({self.get_typ_display()})"


class AuditLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_label = models.CharField(max_length=120)
    object_repr = models.CharField(max_length=255)
    changed_fields = models.JSONField(blank=True, null=True)
    snapshot = models.JSONField(blank=True, null=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="audit_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.model_label}#{self.object_id} {self.action}"


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
    ticket_system_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Ticketsystem E-Mail",
        help_text="An diese Adresse wird nach Genehmigung automatisch gesendet.",
    )
    ticket_header_name = models.CharField(
        max_length=100,
        default="X-Ticket-Nummer",
        verbose_name="Headername Ticketnummer",
    )

    def save(self, *args, **kwargs):
        self.pk = 1  # erzwingt genau einen Datensatz
        super().save(*args, **kwargs)

    def __str__(self):
        return "Globale Einstellungen"


AUDITED_MODELS = (
    Verwaltung,
    Standort,
    Vertrag,
    WanLeitung,
    WanBeauftragung,
    WanBeauftragungProviderKontext,
    Provider,
    ProviderZusatzoption,
    Tarif,
    Erinnerung,
    DokumentAnhang,
    ObjektNotiz,
    SavedFilter,
)


def _serialize_model_instance(instance):
    payload = {}
    for field in instance._meta.concrete_fields:
        if field.name == "id":
            continue
        value = getattr(instance, field.name, None)
        if isinstance(field, models.ForeignKey):
            payload[field.name] = getattr(instance, f"{field.name}_id", None)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            payload[field.name] = value
        else:
            payload[field.name] = str(value)
    return payload


@receiver(pre_save)
def _capture_previous_state(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    if not getattr(instance, "pk", None):
        instance._audit_before = None
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    instance._audit_before = _serialize_model_instance(previous) if previous else None


@receiver(post_save)
def _create_audit_log_on_save(sender, instance, created, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    content_type = ContentType.objects.get_for_model(sender)
    current = _serialize_model_instance(instance)

    if created:
        AuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            action=AuditLog.ACTION_CREATE,
            model_label=instance._meta.label,
            object_repr=str(instance),
            changed_fields=list(current.keys()),
            snapshot=current,
        )
        return

    previous = getattr(instance, "_audit_before", None) or {}
    changed = [key for key, value in current.items() if previous.get(key) != value]
    if not changed:
        return

    AuditLog.objects.create(
        content_type=content_type,
        object_id=instance.pk,
        action=AuditLog.ACTION_UPDATE,
        model_label=instance._meta.label,
        object_repr=str(instance),
        changed_fields=changed,
        snapshot=current,
    )


@receiver(post_delete)
def _create_audit_log_on_delete(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    content_type = ContentType.objects.get_for_model(sender)
    snapshot = _serialize_model_instance(instance)
    AuditLog.objects.create(
        content_type=content_type,
        object_id=instance.pk or 0,
        action=AuditLog.ACTION_DELETE,
        model_label=instance._meta.label,
        object_repr=str(instance),
        changed_fields=[],
        snapshot=snapshot,
    )


def _users_for_ops_notifications():
    return User.objects.filter(
        Q(is_superuser=True)
        | Q(groups__name__in=["SUPERADMIN", "NETZADMIN", "IT-BEAUFTRAGTER", "EINKAEUFER", "EINKAUFER"])
    ).distinct()


@receiver(post_save, sender=Erinnerung)
def _notify_on_reminder(sender, instance, created, **kwargs):
    recipients = []
    if instance.zugewiesen_an_id:
        recipients = [instance.zugewiesen_an]
    else:
        recipients = list(_users_for_ops_notifications())

    if created:
        title = f"Neue Erinnerung: {instance.titel}"
    else:
        title = f"Erinnerung aktualisiert: {instance.titel}"

    for user in recipients:
        UserNotification.objects.create(
            user=user,
            titel=title,
            nachricht=f"Fällig am {instance.faellig_am:%d.%m.%Y} ({instance.get_status_display()})",
            link="/erinnerungen/",
        )


@receiver(post_save, sender=WanBeauftragung)
def _notify_on_beauftragung(sender, instance, created, **kwargs):
    if created:
        title = f"Neue Beauftragung: {instance.titel}"
    else:
        previous = getattr(instance, "_audit_before", None) or {}
        if previous.get("status") == instance.status:
            return
        title = f"Status geändert: {instance.titel}"

    for user in _users_for_ops_notifications():
        UserNotification.objects.create(
            user=user,
            titel=title,
            nachricht=f"Status: {instance.get_status_display()}",
            link=f"/beauftragungen/{instance.pk}/",
        )

