import re

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
    kuerzel = models.CharField(max_length=50, blank=True, null=True)
    typ = models.CharField(
        max_length=50,
        choices=TYP_CHOICES,
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.name


class Standort(models.Model):
    verwaltung = models.ForeignKey(Verwaltung, on_delete=models.CASCADE, related_name="standorte")
    name = models.CharField(max_length=255)
    standort_code = models.CharField(max_length=50, blank=True, null=True)
    adresse_strasse = models.CharField(max_length=255, blank=True, null=True)
    adresse_plz = models.CharField(max_length=10, blank=True, null=True)
    adresse_ort = models.CharField(max_length=100, blank=True, null=True)
    # Gebäudetyp wird in der Oberfläche nicht mehr genutzt, lassen wir aber in der DB
    gebaeude_typ = models.CharField(max_length=50, blank=True, null=True)
    bemerkung = models.TextField(blank=True, null=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["verwaltung__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.verwaltung.kuerzel or self.verwaltung.name})"

    def generate_standort_code(self):
        """
        Kürzel-Verwaltung + erste 3 Buchstaben Ort + erste 3 Buchstaben Straße + Hausnummer:
        - 1     -> 001
        - 1b    -> 01b
        """
        if not self.verwaltung or not self.verwaltung.kuerzel:
            return self.standort_code

        if not self.adresse_ort or not self.adresse_strasse:
            return self.standort_code

        verw_kz = (self.verwaltung.kuerzel or "").upper()

        ort_clean = "".join(self.adresse_ort.split())
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

        street_clean = "".join(street_name.split())
        street_part = street_clean[:3].upper()

        hausnummer_part = ""
        if number_raw:
            m = re.match(r"(\d+)([A-Za-z]*)", number_raw)
            if m:
                digits, letters = m.groups()
                if letters:
                    digits_fmt = digits.zfill(2)
                else:
                    digits_fmt = digits.zfill(3)
                hausnummer_part = f"{digits_fmt}{letters.lower()}"

        return f"{verw_kz}-{ort_part}{street_part}{hausnummer_part}"

    def save(self, *args, **kwargs):
        # Standortkürzel jedes Mal neu berechnen, wenn genug Daten da sind
        new_code = self.generate_standort_code()
        if new_code:
            self.standort_code = new_code
        super().save(*args, **kwargs)


class Vertrag(models.Model):
    verwaltung = models.ForeignKey(Verwaltung, on_delete=models.CASCADE, related_name="vertraege")
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
    rechnungsempfaenger = models.CharField(max_length=255, blank=True, null=True)
    bemerkung_vertrag = models.TextField(blank=True, null=True)

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

    standort = models.ForeignKey(Standort, on_delete=models.CASCADE, related_name="leitungen")
    vertrag = models.ForeignKey(
        Vertrag,
        on_delete=models.SET_NULL,
        related_name="leitungen",
        blank=True,
        null=True,
    )

    # Bezeichnung / Tarif der Leitung
    bezeichnung = models.CharField(max_length=255, blank=True, null=True)

    provider = models.CharField(max_length=255)
    anschlussart = models.CharField(max_length=100, blank=True, null=True)
    bandbreite_down_mbit = models.IntegerField(blank=True, null=True)
    bandbreite_up_mbit = models.IntegerField(blank=True, null=True)
    medium = models.CharField(max_length=50, blank=True, null=True)
    vlan_id = models.IntegerField(blank=True, null=True)
    ip_adressbereich = models.CharField(max_length=50, blank=True, null=True)
    nat_aktiv = models.BooleanField(default=False)
    cpe_geraet = models.CharField(max_length=255, blank=True, null=True)
    cpe_management_ip = models.CharField(max_length=50, blank=True, null=True)
    backup_leitung = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="aktiv")
    inbetriebnahme_datum = models.DateField(blank=True, null=True)
    ausserbetriebnahme_datum = models.DateField(blank=True, null=True)
    bemerkung_technik = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["standort__verwaltung__name", "standort__name", "provider"]

    def __str__(self):
        label = self.bezeichnung or self.provider
        return f"{self.standort} - {label} ({self.bandbreite_down_mbit or '?'} Mbit)"


class UserProfile(models.Model):
    """
    Zusatzinfos zu User:
    - optionale Zuordnung zu einer Verwaltung (für IT-Beauftragte)
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    verwaltung = models.ForeignKey(Verwaltung, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return self.user.username
