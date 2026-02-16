from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import Standort


class Command(BaseCommand):
    help = (
        "Generiert Standortkürzel für Standorte, die z. B. per SQL importiert wurden. "
        "Standard: nur fehlende Kürzel. Mit --all werden alle neu berechnet."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Alle Standortkürzel neu berechnen, auch wenn bereits eins gesetzt ist.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen, welche Änderungen gemacht würden, ohne zu speichern.",
        )

    def handle(self, *args, **options):
        recalc_all = options["all"]
        dry_run = options["dry_run"]

        qs = Standort.objects.select_related("verwaltung").order_by("id")
        if not recalc_all:
            qs = qs.filter(Q(standort_code__isnull=True) | Q(standort_code__exact=""))

        total = qs.count()
        updated = 0
        skipped = 0
        empty = 0

        mode_label = "DRY-RUN" if dry_run else "WRITE"
        self.stdout.write(self.style.NOTICE(f"[{mode_label}] Prüfe {total} Standorte..."))

        for standort in qs:
            old_code = standort.standort_code or ""
            new_code = standort.generate_standort_code() or ""

            if not new_code:
                empty += 1
                continue

            if new_code == old_code:
                skipped += 1
                continue

            updated += 1
            self.stdout.write(
                f"ID {standort.id}: '{old_code or '-'}' -> '{new_code}' ({standort.name})"
            )

            if not dry_run:
                standort.standort_code = new_code
                standort.save(update_fields=["standort_code"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Fertig."))
        self.stdout.write(f"Geprüft: {total}")
        self.stdout.write(f"Aktualisiert: {updated}")
        self.stdout.write(f"Unverändert: {skipped}")
        self.stdout.write(f"Nicht generierbar: {empty}")
