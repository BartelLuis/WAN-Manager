from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.models import LeitungsStoerung, Standort, UserNotification, WanLeitung, Vertrag


class Command(BaseCommand):
    help = "Prueft Datenqualitaet und erzeugt Hinweise als Benachrichtigungen."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts speichern.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        findings = []

        missing_contract_provider = Vertrag.objects.filter(Q(provider_ref__isnull=True) | Q(provider="")).count()
        invalid_lines = WanLeitung.objects.filter(Q(provider="") | Q(medium__isnull=True)).count()
        code_missing = Standort.objects.filter(Q(standort_code__isnull=True) | Q(standort_code="")).count()
        unresolved_incidents = LeitungsStoerung.objects.filter(status__in=[LeitungsStoerung.STATUS_OFFEN, LeitungsStoerung.STATUS_IN_BEARBEITUNG]).count()

        if missing_contract_provider:
            findings.append(f"Vertraege ohne Providerbezug: {missing_contract_provider}")
        if invalid_lines:
            findings.append(f"Leitungen mit unvollstaendigen Feldern: {invalid_lines}")
        if code_missing:
            findings.append(f"Standorte ohne Standortkuerzel: {code_missing}")
        if unresolved_incidents:
            findings.append(f"Offene Stoerungen: {unresolved_incidents}")

        if not findings:
            self.stdout.write(self.style.SUCCESS("Keine Datenqualitaetsprobleme gefunden."))
            return

        self.stdout.write(self.style.WARNING("Datenqualitaetsbefunde:"))
        for item in findings:
            self.stdout.write(f"- {item}")

        if not dry_run:
            from django.contrib.auth.models import User
            admins = User.objects.filter(is_superuser=True)
            text = " | ".join(findings)
            for user in admins:
                UserNotification.objects.create(
                    user=user,
                    titel="Datenqualitaets-Check",
                    nachricht=text,
                    link="/reports/interactive/",
                )

        mode = "DRY-RUN" if dry_run else "WRITE"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Check abgeschlossen am {timezone.localtime():%d.%m.%Y %H:%M}"))
