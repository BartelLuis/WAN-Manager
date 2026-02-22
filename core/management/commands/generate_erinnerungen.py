from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Erinnerung, Vertrag, WanBeauftragung


class Command(BaseCommand):
    help = "Erzeugt Erinnerungen fuer auslaufende Vertraege und faellige WAN-Beauftragungen."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Horizont in Tagen fuer bevorstehende Faelligkeiten.")
        parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts speichern.")

    def handle(self, *args, **options):
        horizon_days = max(0, options["days"])
        dry_run = options["dry_run"]

        today = timezone.localdate()
        horizon = today + timedelta(days=horizon_days)
        created = 0

        self._mark_overdue(today, dry_run)

        vertraege = Vertrag.objects.filter(laufzeit_bis__isnull=False, laufzeit_bis__lte=horizon)
        for vertrag in vertraege:
            if self._ensure_contract_reminder(vertrag, today, dry_run):
                created += 1

        beauftragungen = WanBeauftragung.objects.filter(
            umsetzung_bis__isnull=False,
            umsetzung_bis__lte=horizon,
        ).exclude(status__in=[WanBeauftragung.STATUS_UMGESETZT, WanBeauftragung.STATUS_ABGELEHNT, WanBeauftragung.STATUS_STORNIERT])

        for beauftragung in beauftragungen:
            if self._ensure_beauftragung_reminder(beauftragung, today, dry_run):
                created += 1

        mode = "DRY-RUN" if dry_run else "WRITE"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Erinnerungen neu: {created}"))

    def _mark_overdue(self, today, dry_run):
        qs = Erinnerung.objects.filter(status=Erinnerung.STATUS_OFFEN, faellig_am__lt=today)
        count = qs.count()
        if count and not dry_run:
            qs.update(status=Erinnerung.STATUS_UEBERFAELLIG)
        if count:
            self.stdout.write(f"Ueberfaellig markiert: {count}")

    def _ensure_contract_reminder(self, vertrag, today, dry_run):
        title = f"Vertrag laeuft aus: {vertrag.vertragsnummer}"
        exists = Erinnerung.objects.filter(
            typ=Erinnerung.TYP_VERTRAG,
            vertrag=vertrag,
            titel=title,
            faellig_am=vertrag.laufzeit_bis,
        ).exists()
        if exists:
            return False

        if not dry_run:
            status = Erinnerung.STATUS_UEBERFAELLIG if vertrag.laufzeit_bis < today else Erinnerung.STATUS_OFFEN
            Erinnerung.objects.create(
                titel=title,
                typ=Erinnerung.TYP_VERTRAG,
                status=status,
                faellig_am=vertrag.laufzeit_bis,
                vertrag=vertrag,
            )
        return True

    def _ensure_beauftragung_reminder(self, beauftragung, today, dry_run):
        title = f"Beauftragung faellig: {beauftragung.titel}"
        exists = Erinnerung.objects.filter(
            typ=Erinnerung.TYP_BEAUFTRAGUNG,
            beauftragung=beauftragung,
            titel=title,
            faellig_am=beauftragung.umsetzung_bis,
        ).exists()
        if exists:
            return False

        if not dry_run:
            status = Erinnerung.STATUS_UEBERFAELLIG if beauftragung.umsetzung_bis < today else Erinnerung.STATUS_OFFEN
            Erinnerung.objects.create(
                titel=title,
                typ=Erinnerung.TYP_BEAUFTRAGUNG,
                status=status,
                faellig_am=beauftragung.umsetzung_bis,
                beauftragung=beauftragung,
            )
        return True
